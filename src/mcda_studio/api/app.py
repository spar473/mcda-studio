"""FastAPI application factory. Thin by design: routing, error mapping and serialisation only."""

import os
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.routing import Match

import mcda_studio.methods  # noqa: F401  (registers built-in methods)
from mcda_studio.api import operations as ops
from mcda_studio.api import schemas as sc
from mcda_studio.api.errors import ApiError, from_mcda_error, install_handlers
from mcda_studio.api.model_comparisons import router as models_router
from mcda_studio.api.proposals import ProposalBodyLimit
from mcda_studio.api.proposals import router as proposals_router
from mcda_studio.api.proxy import router as proxy_router
from mcda_studio.domain.analysis_record import (
    AnyAnalysisExportDocument,
    AnyAnalysisRecord,
)
from mcda_studio.domain.comparison import MethodComparison
from mcda_studio.domain.criteria import ALLOWED_VALUE_FUNCTIONS, Direction
from mcda_studio.domain.decision import DecisionRecord
from mcda_studio.domain.errors import (
    McdaError,
    MethodNotSupportedError,
    ModelStructureError,
    ProjectLoadError,
)
from mcda_studio.domain.feasibility import FeasibilityResult
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import (
    AnalysisValidation,
    SensitivityProbe,
    SortingSensitivityProbe,
    ValueFunctionPreview,
    WeightPreview,
)
from mcda_studio.domain.project import SCHEMA_VERSION, Project
from mcda_studio.domain.results import (
    AhpMatrixPreview,
    AhpResult,
    AnalysisResultUnion,
    MavtResult,
    MavtSortingResult,
    PrometheeResult,
    ScenarioComparison,
    SensitivityResult,
    SmaaResult,
    SortingSensitivityResult,
)
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.base import available_methods, get_method
from mcda_studio.runtime import asset_directory, build_identity, package_version
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import calculation_workspace_service as calculations
from mcda_studio.services import comparison_service as comparisons
from mcda_studio.services import decision_record_service as decisions
from mcda_studio.services import derived_service as derived
from mcda_studio.services import evidence_compilation_service as evidence_compilation
from mcda_studio.services import evidence_workspace_service as evidence_workspace
from mcda_studio.services import factor_analysis_service as factor_analysis
from mcda_studio.services import feasibility_service as feasibility
from mcda_studio.services import project_service as ps
from mcda_studio.services import provenance_service as provenance
from mcda_studio.services import questions_service as questions
from mcda_studio.services import results_service as results
from mcda_studio.services import templates
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text
from mcda_studio.storage.library_backup import ensure_restore_complete
from mcda_studio.storage.project_store import ProjectStore, StoredProject

DEFAULT_STORE = Path("~/.mcda-studio/projects")
ENV_STORE = "MCDA_STUDIO_PROJECTS"
ENV_EXAMPLES = "MCDA_STUDIO_EXAMPLES"
ENV_FRONTEND = "MCDA_STUDIO_FRONTEND"
_LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]


def _strip_etag(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if v.startswith("W/"):
        v = v[2:]
    return v.strip('"') or None


def _document(
    project: Project, updated_at: Any = None, report: ValidationReport | None = None
) -> sc.ProjectDocument:
    return sc.ProjectDocument(
        project=project,
        fingerprint=project.fingerprint(),
        updated_at=updated_at,
        validation=report if report is not None else svc.validate(project),
    )


def _stored_document(stored: StoredProject) -> sc.ProjectDocument:
    return _document(stored.project, stored.updated_at)


def _summary(stored: StoredProject) -> sc.ProjectSummary:
    p = stored.project
    try:
        tree = p.tree()
        criteria, leaves = len(tree), len(tree.leaves())
    except ModelStructureError:
        criteria, leaves = len(p.criteria), 0
    report = svc.validate(p)
    return sc.ProjectSummary(
        id=p.id,
        title=p.title,
        description=p.description,
        decision_maker=p.decision_maker,
        alternatives=len(p.alternatives),
        criteria=criteria,
        leaves=leaves,
        scenarios=len(p.scenarios),
        updated_at=stored.updated_at,
        fingerprint=stored.fingerprint,
        validation=sc.ValidationSummary(
            ok=report.ok, errors=len(report.errors), warnings=len(report.warnings)
        ),
    )


def _require_sound_structure(project: Project) -> None:
    """Semantic incompleteness may be saved (it is a draft); a corrupt tree may not."""
    project.tree()  # raises ModelStructureError (duplicate ids, unknown parent, cycle)


#: Sensitivity bodies by method: a sorting body is the MAVT body plus class changes. The subtype is
#: listed first so that serialisation keeps its extra fields.
AnySensitivityResult = SortingSensitivityResult | SensitivityResult
AnySensitivityProbe = SortingSensitivityProbe | SensitivityProbe


ApiResult = MavtResult | MavtSortingResult | SmaaResult | PrometheeResult | AhpResult


def _evaluate(project: Project, configuration: AnalysisConfiguration | None) -> ApiResult:
    result = svc.evaluate_project(project, configuration)
    if not isinstance(result, ApiResult):
        # Only a method whose result type is in the API union can be served.
        method = get_method(result.method)
        raise MethodNotSupportedError(method.name, "evaluate", sorted(method.capabilities))
    return result


def get_store(request: Request) -> ProjectStore:
    store: ProjectStore = request.app.state.store
    return store


Store = Annotated[ProjectStore, Depends(get_store)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _router(examples_dir: Path | None, frontend: Path | None) -> APIRouter:
    r = APIRouter(prefix="/api")
    repo = JsonProjectRepository()

    # ---- service info --------------------------------------------------------------------
    @r.get("/health", response_model=sc.Health, tags=["service"])
    def health(store: Store) -> sc.Health:
        return sc.Health(
            version=package_version(),
            schema_version=SCHEMA_VERSION,
            methods=available_methods(),
            store=str(store.root),
            build=build_identity(frontend),
        )

    @r.get("/meta", response_model=sc.Meta, tags=["service"])
    def meta() -> sc.Meta:
        """Scale types, value-function kinds and which combinations the engine accepts."""
        kinds = ["linear", "piecewise_linear", "qualitative", "direct_rating"]
        return sc.Meta(
            scale_types=[
                sc.ScaleTypeInfo(
                    type=t,
                    numeric=Scale(type=t).is_numeric,
                    labelled=Scale(type=t).is_labelled,
                    allowed_value_functions=[k for k in kinds if k in ALLOWED_VALUE_FUNCTIONS[t]],
                )
                for t in ScaleType
            ],
            value_function_kinds=kinds,
            anchor_modes=list(AnchorMode),
            directions=list(Direction),
            out_of_domain_policies=["error", "clamp"],
            methods=[
                sc.MethodInfo(
                    name=m.name,
                    label=m.label,
                    capabilities=sorted(m.capabilities),
                    export_tables=list(results.EXPORT_TABLES.get(m.name, ())),
                )
                for m in map(get_method, available_methods())
            ],
        )

    @r.get("/templates", response_model=list[sc.TemplateInfo], tags=["service"])
    def list_templates() -> list[sc.TemplateInfo]:
        return [sc.TemplateInfo(name=n) for n in sorted(templates.TEMPLATES)]

    def example_dirs() -> dict[str, Path]:
        if examples_dir is None or not examples_dir.is_dir():
            return {}
        return {
            d.name: d / "project.json"
            for d in sorted(examples_dir.iterdir())
            if (d / "project.json").is_file()
        }

    @r.get("/examples", response_model=list[sc.ExampleInfo], tags=["service"])
    def list_examples() -> list[sc.ExampleInfo]:
        out: list[sc.ExampleInfo] = []
        for name, path in example_dirs().items():
            try:
                p = repo.load(path)
            except McdaError:
                continue
            out.append(
                sc.ExampleInfo(
                    name=name,
                    project_id=p.id,
                    title=p.title,
                    description=p.description,
                    alternatives=len(p.alternatives),
                    criteria=len(p.criteria),
                )
            )
        return out

    @r.get("/trash", response_model=list[sc.TrashEntry], tags=["projects"])
    def list_trash(store: Store) -> list[sc.TrashEntry]:
        """List recovery entries, including unreadable entries. Nothing is removed."""
        from dataclasses import asdict

        return [sc.TrashEntry(**asdict(entry)) for entry in store.list_trash()]

    @r.post(
        "/trash/{entry}/restore",
        response_model=sc.ProjectDocument,
        status_code=201,
        tags=["projects"],
        responses={
            409: {"description": "Active ID conflict or library owned by another writer"},
            422: {"description": "Unsafe or unreadable recovery entry"},
            404: {"description": "Recovery entry not found"},
            500: {"description": "Publication failed; recovery data retained"},
        },
    )
    def restore_project(
        entry: str, req: sc.RestoreRequest, store: Store, response: Response
    ) -> sc.ProjectDocument:
        """Restore without overwrite. Both modes retain the original recovery entry."""
        restored = store.restore(entry, as_copy=req.as_copy)
        response.headers["Location"] = f"/api/projects/{restored.project.id}"
        response.headers["ETag"] = f'"{restored.fingerprint}"'
        return _stored_document(restored)

    # ---- projects ------------------------------------------------------------------------
    @r.get("/projects", response_model=sc.ProjectList, tags=["projects"])
    def list_projects(store: Store) -> sc.ProjectList:
        found, unreadable = store.list()
        return sc.ProjectList(
            projects=[_summary(s) for s in found],
            unreadable=[sc.UnreadableFile(file=u.file, error=u.error) for u in unreadable],
        )

    @r.post("/projects", response_model=sc.ProjectDocument, status_code=201, tags=["projects"])
    def create_project(
        req: sc.CreateProjectRequest, store: Store, response: Response
    ) -> sc.ProjectDocument:
        project = templates.from_template(req.template, req.title)
        project = ps.update_project_details(
            project,
            description=req.description or None,
            decision_maker=req.decision_maker or None,
        )
        if req.method != project.analysis.method:
            project = project.model_copy(
                update={"analysis": project.analysis.model_copy(update={"method": req.method})}
            )
        stored = store.create(project)
        response.headers["Location"] = f"/api/projects/{stored.project.id}"
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        return _stored_document(stored)

    @r.post(
        "/projects/import",
        response_model=sc.ImportedProjectDocument,
        status_code=201,
        tags=["projects"],
    )
    def import_project(
        raw: dict[str, Any],
        store: Store,
        response: Response,
        on_conflict: Annotated[sc.OnConflict, Query()] = "error",
    ) -> sc.ImportedProjectDocument:
        """Store a project file's contents (schema-checked and migrated like any file load).

        A separate copy gets a new ID, so its fingerprint differs from the file's; the returned
        receipt records that single transformation instead of rebinding any provenance."""
        try:
            project = repo.from_dict(raw)
        except ProjectLoadError as exc:
            raise ApiError(
                422, "INVALID_PROJECT_FILE", str(exc).splitlines()[0], _file_details(str(exc))
            ) from exc
        _require_sound_structure(project)
        receipt = None
        if on_conflict == "new_id" and store.exists(project.id):
            original = project
            project = ps.duplicate_project(project, title=project.title)
            receipt = provenance.copy_receipt(original, project)
        stored = store.create(project)
        response.headers["Location"] = f"/api/projects/{stored.project.id}"
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        document = _stored_document(stored)
        return sc.ImportedProjectDocument(
            project=document.project,
            fingerprint=document.fingerprint,
            updated_at=document.updated_at,
            validation=document.validation,
            copy_receipt=receipt,
        )

    @r.get("/projects/{project_id}", response_model=sc.ProjectDocument, tags=["projects"])
    def get_project(project_id: str, store: Store, response: Response) -> sc.ProjectDocument:
        stored = store.get(project_id)
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        return _stored_document(stored)

    @r.put("/projects/{project_id}", response_model=sc.ProjectDocument, tags=["projects"])
    def save_project(
        project_id: str,
        project: Project,
        store: Store,
        response: Response,
        if_match: IfMatch = None,
    ) -> sc.ProjectDocument:
        """Replace the stored project. Identity is the URL id: the body must carry the same id."""
        if project.id != project_id:
            raise ApiError(
                422,
                "ID_MISMATCH",
                f"the URL names project {project_id!r} but the body carries id {project.id!r}",
                [{"path": "body.id", "message": "must equal the id in the URL"}],
            )
        if not project.required_schema_version() <= project.schema_version <= SCHEMA_VERSION:
            raise ApiError(
                422,
                "UNSUPPORTED_SCHEMA_VERSION",
                f"schema_version {project.schema_version} cannot hold this project (it needs "
                f"{project.required_schema_version()} to {SCHEMA_VERSION}); "
                "use the import endpoint to migrate older files",
            )
        _require_sound_structure(project)
        stored = store.replace(project, _strip_etag(if_match))
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        return _stored_document(stored)

    @r.delete("/projects/{project_id}", status_code=204, tags=["projects"])
    def delete_project(project_id: str, store: Store) -> Response:
        """Moves the file to ``<store>/.trash/``; it is not unlinked."""
        store.delete(project_id)
        return Response(status_code=204)

    @r.post(
        "/projects/{project_id}/duplicate",
        response_model=sc.ProjectDocument,
        status_code=201,
        tags=["projects"],
    )
    def duplicate_project(
        project_id: str, req: sc.DuplicateRequest, store: Store, response: Response
    ) -> sc.ProjectDocument:
        """An independent deep copy under a fresh id; the original is untouched."""
        clone = ps.duplicate_project(store.get(project_id).project, req.title)
        stored = store.create(clone)
        response.headers["Location"] = f"/api/projects/{stored.project.id}"
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        return _stored_document(stored)

    @r.get("/projects/{project_id}/file", tags=["projects"])
    def download_project(project_id: str, store: Store) -> Response:
        """The project exactly as it is written to disk (deterministic JSON)."""
        project = store.get(project_id).project
        return Response(
            to_json_text(project),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{project.id}.json"'},
        )

    @r.post(
        "/examples/{name}/import",
        response_model=sc.ProjectDocument,
        status_code=201,
        tags=["service"],
    )
    def import_example(
        name: str,
        store: Store,
        response: Response,
        on_conflict: Annotated[sc.OnConflict, Query()] = "error",
    ) -> sc.ProjectDocument:
        path = example_dirs().get(name)
        if path is None:
            raise ApiError(404, "EXAMPLE_NOT_FOUND", f"no bundled example named {name!r}")
        project = repo.load(path)
        if on_conflict == "new_id" and store.exists(project.id):
            project = ps.duplicate_project(project, title=project.title)
        stored = store.create(project)
        response.headers["Location"] = f"/api/projects/{stored.project.id}"
        response.headers["ETag"] = f'"{stored.fingerprint}"'
        return _stored_document(stored)

    # ---- stateless editing (the client owns the unsaved working copy) ----------------------
    @r.post("/edit", response_model=sc.ProjectDocument, tags=["editing"])
    def edit(req: sc.EditRequest) -> sc.ProjectDocument:
        """Apply operations in order to the project in the body; nothing is stored.

        All-or-nothing: if operation *i* is refused the response names ``operations[i]`` and no
        change is returned.
        """
        project = req.project
        for i, operation in enumerate(req.operations):
            try:
                project = ops.apply_operation(project, operation)
            except McdaError as exc:
                raise from_mcda_error(exc, f"operations[{i}]") from exc
        return _document(project)

    # ---- validation and analysis (drafts in the body, or stored projects by id) -------------
    @r.post("/validate", response_model=ValidationReport, tags=["analysis"])
    def validate_draft(req: sc.DraftRequest) -> ValidationReport:
        return svc.validate(req.project)

    @r.get("/projects/{project_id}/validation", response_model=ValidationReport, tags=["analysis"])
    def validate_stored(project_id: str, store: Store) -> ValidationReport:
        return svc.validate(store.get(project_id).project)

    @r.post("/analysis/record", response_model=AnyAnalysisRecord, tags=["analysis"])
    def completed_analysis(req: sc.EvaluateDraftRequest) -> results.AnyRecord:
        """Version 1 for MAVT; version 2 for every other method that has a record."""
        return results.analysis_record(req.project, req.configuration)

    @r.post(
        "/projects/{project_id}/analysis/record",
        response_model=AnyAnalysisRecord,
        tags=["analysis"],
    )
    def completed_stored_analysis(
        project_id: str, opts: sc.AnalysisOptions, store: Store
    ) -> results.AnyRecord:
        return results.analysis_record(store.get(project_id).project, opts.configuration)

    def download_analysis(project: Project, opts: sc.AnalysisExportOptions) -> Response:
        data, media, filename, record = results.export_analysis(
            project,
            opts.configuration,
            opts.expected_project_fingerprint,
            opts.expected_record_digest,
            opts.format,
            opts.table,
            opts.presentation,
        )
        return Response(
            content=data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Analysis-Record-Digest": record.record_digest,
                "X-Project-Fingerprint": record.result.project_fingerprint,
            },
        )

    export_responses: dict[int | str, dict[str, Any]] = {
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "A context-verified JSON document or full-precision CSV attachment.",
        }
    }

    @r.post(
        "/analysis/export",
        response_model=AnyAnalysisExportDocument,
        responses=export_responses,
        tags=["analysis"],
    )
    def export_draft(req: sc.AnalysisExportRequest) -> Response:
        return download_analysis(req.project, req)

    @r.post(
        "/projects/{project_id}/analysis/export",
        response_model=AnyAnalysisExportDocument,
        responses=export_responses,
        tags=["analysis"],
    )
    def export_stored(project_id: str, opts: sc.AnalysisExportOptions, store: Store) -> Response:
        return download_analysis(store.get(project_id).project, opts)

    @r.post("/analysis/validate", response_model=AnalysisValidation, tags=["analysis"])
    def validate_effective(req: sc.EvaluateDraftRequest) -> AnalysisValidation:
        return svc.validate_effective(req.project, req.configuration)

    @r.post("/value-functions/preview", response_model=ValueFunctionPreview, tags=["analysis"])
    def preview_value_function(req: sc.ValueFunctionPreviewRequest) -> ValueFunctionPreview:
        """Inspect a criterion/candidate without saving or requiring unrelated complete data."""
        return svc.preview_value_function(
            req.project, req.criterion_id, req.configuration, req.candidate, req.sample_count
        )

    @r.post("/weights/preview", response_model=WeightPreview, tags=["analysis"])
    def preview_weights(req: sc.EvaluateDraftRequest) -> WeightPreview:
        """Derive complete weights independently of measurements; never impute missing ratings."""
        return svc.preview_weights(req.project, req.configuration)

    @r.post("/open-questions", response_model=questions.QuestionsResult, tags=["analysis"])
    def open_questions_draft(req: sc.OpenQuestionsRequest) -> questions.QuestionsResult:
        return questions.open_questions(
            req.project,
            req.configuration,
            req.dossier,
            req.factor_record,
            req.proposals,
            req.model_comparison,
            req.proxy,
        )

    @r.post(
        "/factor-uncertainty/inspect",
        response_model=factor_analysis.FactorInspection,
        tags=["analysis"],
    )
    def inspect_factor_uncertainty(
        req: sc.FactorInspectRequest,
    ) -> factor_analysis.FactorInspection:
        """Inspect local factor assumptions and dependency questions; never accept or write them."""
        return factor_analysis.inspect(req.project, req.model, req.uncertainty)

    @r.post(
        "/factor-uncertainty/run", response_model=factor_analysis.FactorRunRecord, tags=["analysis"]
    )
    def run_factor_uncertainty(req: sc.FactorRunRequest) -> factor_analysis.FactorRunRecord:
        """Separate factor-based MAVT, sorting or SMAA-2 run; no project or library changes."""
        return factor_analysis.run(
            req.project, req.model, req.uncertainty, req.parameters, req.decision
        )

    @r.post(
        "/factor-uncertainty/verify",
        response_model=factor_analysis.FactorRunRecord,
        tags=["analysis"],
    )
    def verify_factor_uncertainty(req: sc.FactorVerifyRequest) -> factor_analysis.FactorRunRecord:
        """Verify a retained snapshot, optionally replaying in the recorded environment."""
        return factor_analysis.verify(req.record, req.replay)

    @r.post("/derived/preview", response_model=derived.DerivedPreview, tags=["analysis"])
    def preview_derived(req: sc.DerivedPreviewRequest) -> derived.DerivedPreview:
        return derived.preview_document(req.project, req.model)

    @r.post("/derived/compile", response_model=derived.DerivedCompilation, tags=["analysis"])
    def compile_derived(req: sc.DerivedCompileRequest) -> derived.DerivedCompilation:
        """Return a reviewed static copy with provenance; never write project/library files."""
        return derived.compilation_bundle(req.project, req.model, req.expected_review_digest)

    @r.post(
        "/calculations/inspect",
        response_model=calculations.CalculationInspection,
        tags=["analysis"],
    )
    def inspect_calculations(
        req: sc.CalculationInspectRequest,
    ) -> calculations.CalculationInspection:
        """Replay a calculation workspace (or start one from a model); nothing is written."""
        return calculations.inspect(req.project, req.document)

    @r.post(
        "/calculations/propose",
        response_model=calculations.CalculationInspection,
        tags=["analysis"],
    )
    def propose_calculation(
        req: sc.CalculationProposeRequest,
    ) -> calculations.CalculationInspection:
        """Return a candidate workspace with one more event, for explicit confirmation."""
        return calculations.propose(
            req.project, req.workspace, req.event, req.expected_review_digest
        )

    @r.post(
        "/calculations/apply",
        response_model=calculations.CalculationApplication,
        tags=["analysis"],
    )
    def apply_calculation(req: sc.CalculationApplyRequest) -> calculations.CalculationApplication:
        """Recompile the acknowledged preview; the client applies the returned assignments as one
        edit. Nothing is written: the project in the body, its stored file and the library are
        unchanged."""
        return calculations.apply(
            req.project, req.workspace, req.expected_review_digest, req.recorded_by, req.recorded_at
        )

    @r.post(
        "/evidence/inspect", response_model=evidence_workspace.EvidenceInspection, tags=["evidence"]
    )
    def inspect_evidence(req: sc.EvidenceInspectRequest) -> evidence_workspace.EvidenceInspection:
        """Inspect local evidence without accepting claims or writing files."""
        return evidence_workspace.inspect(req.project, req.document)

    @r.post(
        "/evidence/review", response_model=evidence_workspace.EvidenceInspection, tags=["evidence"]
    )
    def review_evidence(req: sc.EvidenceReviewRequest) -> evidence_workspace.EvidenceInspection:
        """Propose one explicit review in a returned copy; no project/library mutation."""
        return evidence_workspace.propose_review(
            req.project, req.workspace, req.event, req.expected_review_digest
        )

    @r.post(
        "/evidence/compile",
        response_model=evidence_compilation.EvidenceCompilation,
        tags=["evidence"],
    )
    def compile_evidence(
        req: sc.EvidenceCompileRequest,
    ) -> evidence_compilation.EvidenceCompilation:
        """Revalidate the acknowledged preview and return a separate copy with its history.

        Nothing is written: the current project, its saved bytes and the library are unchanged."""
        return evidence_compilation.compilation_bundle(
            req.project, req.workspace, req.expected_review_digest, req.expected_workspace_digest
        )

    @r.post(
        "/evidence/compilation/inspect",
        response_model=evidence_compilation.EvidenceCompilationInspection,
        tags=["evidence"],
    )
    def inspect_evidence_compilation(
        req: sc.EvidenceCompilationInspectRequest,
    ) -> evidence_compilation.EvidenceCompilationInspection:
        """Verify a bundle by replay and reconstruction, then inspect it without rebinding."""
        return evidence_compilation.inspect(req.project, req.bundle)

    @r.post("/decisions/preview", response_model=decisions.DecisionRecordV2, tags=["decisions"])
    def preview_decision(req: sc.DecisionPreviewRequest) -> decisions.DecisionRecordV2:
        """Create a version-2 record in memory for review and export; nothing is stored."""
        previous = _decision_record(req.predecessor, "predecessor")
        return decisions.create(req.project, req.details, req.artifacts, previous)

    @r.post(
        "/decisions/inspect",
        response_model=decisions.DecisionRecordInspection,
        tags=["decisions"],
    )
    def inspect_decision(req: sc.DecisionInspectRequest) -> decisions.DecisionRecordInspection:
        """Verify a version-1 or version-2 record and read it against the current project."""
        record = _decision_record(req.record, "record")
        assert record is not None
        return decisions.inspect(
            req.project, record, _decision_record(req.predecessor, "predecessor")
        )

    @r.post("/provenance/binding", response_model=provenance.ArtifactBinding, tags=["evidence"])
    def bind_artifact(req: sc.ArtifactBindingRequest) -> provenance.ArtifactBinding:
        """Relate the current project to a verified artifact by exact fingerprints only."""
        return provenance.bind(req.project, req.artifact, req.copy_receipt)

    @r.post("/methods/compare", response_model=MethodComparison, tags=["analysis"])
    def compare_methods_draft(req: sc.MethodComparisonRequest) -> MethodComparison:
        """Every requested method's own reading of the project, side by side; a method that cannot
        read it is a column with its typed error. 422 UNKNOWN_REFERENCE for an unregistered method.
        No number combines two methods."""
        return comparisons.compare_methods(req.project, req.configuration, req.methods)

    @r.post(
        "/projects/{project_id}/methods/compare", response_model=MethodComparison, tags=["analysis"]
    )
    def compare_methods_stored(
        project_id: str, opts: sc.MethodComparisonOptions, store: Store
    ) -> MethodComparison:
        return comparisons.compare_methods(
            store.get(project_id).project, opts.configuration, opts.methods
        )

    def download_comparison(project: Project, opts: sc.MethodComparisonExportOptions) -> Response:
        data, media, filename, comparison = comparisons.export_comparison(
            project,
            opts.configuration,
            opts.methods,
            opts.expected_project_fingerprint,
            opts.format,
        )
        return Response(
            content=data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Project-Fingerprint": comparison.project_fingerprint,
            },
        )

    comparison_responses: dict[int | str, dict[str, Any]] = {
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "The comparison as a JSON document or a long CSV attachment.",
        }
    }

    @r.post(
        "/methods/compare/export",
        response_model=MethodComparison,
        responses=comparison_responses,
        tags=["analysis"],
    )
    def export_comparison_draft(req: sc.MethodComparisonExportRequest) -> Response:
        return download_comparison(req.project, req)

    @r.post(
        "/projects/{project_id}/methods/compare/export",
        response_model=MethodComparison,
        responses=comparison_responses,
        tags=["analysis"],
    )
    def export_comparison_stored(
        project_id: str, opts: sc.MethodComparisonExportOptions, store: Store
    ) -> Response:
        return download_comparison(store.get(project_id).project, opts)

    @r.post("/feasibility", response_model=FeasibilityResult, tags=["analysis"])
    def check_feasibility_draft(req: sc.FeasibilityRequest) -> FeasibilityResult:
        """Pass, fail or unknown per alternative and requirement, outside any method. 422
        VALIDATION_FAILED when the requirements have errors or there are none."""
        return feasibility.check_feasibility(req.project)

    @r.post(
        "/projects/{project_id}/feasibility", response_model=FeasibilityResult, tags=["analysis"]
    )
    def check_feasibility_stored(project_id: str, store: Store) -> FeasibilityResult:
        return feasibility.check_feasibility(store.get(project_id).project)

    def download_feasibility(project: Project, opts: sc.FeasibilityExportOptions) -> Response:
        data, media, filename, result = feasibility.export_feasibility(
            project, opts.expected_project_fingerprint, opts.format
        )
        return Response(
            content=data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Project-Fingerprint": result.project_fingerprint,
            },
        )

    feasibility_responses: dict[int | str, dict[str, Any]] = {
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "The feasibility check as a JSON document or a CSV attachment.",
        }
    }

    @r.post(
        "/feasibility/export",
        response_model=FeasibilityResult,
        responses=feasibility_responses,
        tags=["analysis"],
    )
    def export_feasibility_draft(req: sc.FeasibilityExportRequest) -> Response:
        return download_feasibility(req.project, req)

    @r.post(
        "/projects/{project_id}/feasibility/export",
        response_model=FeasibilityResult,
        responses=feasibility_responses,
        tags=["analysis"],
    )
    def export_feasibility_stored(
        project_id: str, opts: sc.FeasibilityExportOptions, store: Store
    ) -> Response:
        return download_feasibility(store.get(project_id).project, opts)

    @r.post("/ahp/preview", response_model=AhpMatrixPreview, tags=["analysis"])
    def preview_ahp_matrix(req: sc.AhpPreviewRequest) -> AhpMatrixPreview:
        """Read-only priorities and consistency of one drafted AHP matrix. An incomplete matrix
        returns its issues and no analysis; nothing is saved."""
        return svc.preview_ahp_matrix(req.items, req.judgements)

    @r.post("/evaluate", response_model=AnalysisResultUnion, tags=["analysis"])
    def evaluate_draft(req: sc.EvaluateDraftRequest) -> ApiResult:
        """Evaluation of the project in the body by its configured method, tagged by ``method``.
        422 VALIDATION_FAILED if it has errors."""
        return _evaluate(req.project, req.configuration)

    @r.post(
        "/projects/{project_id}/evaluate", response_model=AnalysisResultUnion, tags=["analysis"]
    )
    def evaluate_stored(project_id: str, opts: sc.AnalysisOptions, store: Store) -> ApiResult:
        return _evaluate(store.get(project_id).project, opts.configuration)

    @r.post("/sensitivity", response_model=AnySensitivityResult, tags=["analysis"])
    def sensitivity_draft(req: sc.SensitivityDraftRequest) -> SensitivityResult:
        return svc.sensitivity(req.project, req.node_id, req.configuration, req.steps)

    @r.post(
        "/projects/{project_id}/sensitivity", response_model=AnySensitivityResult, tags=["analysis"]
    )
    def sensitivity_stored(
        project_id: str, opts: sc.SensitivityOptions, store: Store
    ) -> SensitivityResult:
        return svc.sensitivity(
            store.get(project_id).project, opts.node_id, opts.configuration, opts.steps
        )

    @r.post("/sensitivity/probe", response_model=AnySensitivityProbe, tags=["analysis"])
    def sensitivity_probe_draft(req: sc.SensitivityProbeRequest) -> SensitivityProbe:
        """Exact scores at one hypothetical local weight; reads only, persists nothing."""
        return svc.sensitivity_probe(req.project, req.node_id, req.weight, req.configuration)

    @r.post(
        "/projects/{project_id}/sensitivity/probe",
        response_model=AnySensitivityProbe,
        tags=["analysis"],
    )
    def sensitivity_probe_stored(
        project_id: str, opts: sc.SensitivityProbeOptions, store: Store
    ) -> SensitivityProbe:
        return svc.sensitivity_probe(
            store.get(project_id).project, opts.node_id, opts.weight, opts.configuration
        )

    @r.post("/scenarios/compare", response_model=ScenarioComparison, tags=["analysis"])
    def compare_draft(req: sc.CompareDraftRequest) -> ScenarioComparison:
        return svc.compare_scenarios(req.project, req.scenario_ids, req.configuration)

    @r.post(
        "/projects/{project_id}/scenarios/compare",
        response_model=ScenarioComparison,
        tags=["analysis"],
    )
    def compare_stored(
        project_id: str, opts: sc.CompareOptions, store: Store
    ) -> ScenarioComparison:
        return svc.compare_scenarios(
            store.get(project_id).project, opts.scenario_ids, opts.configuration
        )

    return r


_DECISION_RECORDS: TypeAdapter[DecisionRecord | decisions.DecisionRecordV2] = TypeAdapter(
    sc.AnyDecisionRecord
)


def _decision_record(
    raw: dict[str, Any] | None, field: str
) -> DecisionRecord | decisions.DecisionRecordV2 | None:
    if raw is None:
        return None
    try:
        return _DECISION_RECORDS.validate_python(raw)
    except ValidationError as exc:
        details = [
            {"path": f"{field}." + ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()[:20]
        ]
        raise ApiError(
            422, "INVALID_DECISION_RECORD", f"{field} is not a valid decision record", details
        ) from exc


def _file_details(text: str) -> list[dict[str, Any]]:
    lines = [ln for ln in text.splitlines()[1:] if ln.strip()]
    return [{"path": "", "message": ln} for ln in lines[:20]]


_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def create_app(
    store_dir: str | Path | None = None,
    examples_dir: str | Path | None = None,
    frontend_dir: str | Path | Literal[False] | None = None,
) -> FastAPI:
    """Build the application. Arguments override the ``MCDA_STUDIO_*`` environment variables,
    which override source-checkout assets and then bundled package resources. The library
    defaults to ``~/.mcda-studio/projects``. ``frontend_dir=False`` serves only the API;
    ``None`` means "find it"."""
    assets = ExitStack()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            ensure_restore_complete(app.state.store.root)
            with app.state.store.ownership():
                yield
        finally:
            assets.close()

    app = FastAPI(
        lifespan=lifespan,
        title="MCDA Studio API",
        version=package_version(),
        summary="Create, edit, store, validate and evaluate multi-criteria decision models.",
        description=(
            "Every body is a domain model; the saved project schema is the single source of "
            "truth. No mathematics lives here. See docs/api/contract.md."
        ),
    )
    store_path = Path(store_dir or os.environ.get(ENV_STORE) or DEFAULT_STORE)
    app.state.store = ProjectStore(store_path)

    examples = asset_directory("examples", examples_dir, assets)
    dist = None if frontend_dir is False else asset_directory("frontend", frontend_dir, assets)
    app.state.frontend_dir = dist
    app.state.examples_dir = examples

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_LOCAL_HOSTS)
    install_handlers(app)
    app.add_middleware(ProposalBodyLimit)
    app.include_router(_router(examples, dist))
    app.include_router(proposals_router)
    app.include_router(models_router)
    app.include_router(proxy_router)

    @app.api_route(
        "/api/{rest:path}", methods=_ALL_METHODS, include_in_schema=False, response_model=None
    )
    def unknown_api_route(rest: str, request: Request) -> NoReturn:
        """Registered after every real route, so it only sees what nothing else handled. Without
        it, a mounted frontend would answer an API typo with an HTML page or a bare 405."""
        path = request.url.path
        allowed = sorted(
            method
            for method in _ALL_METHODS
            if method != "HEAD"  # implied by GET
            if any(
                route.matches({**request.scope, "method": method})[0] == Match.FULL
                for route in request.app.router.routes
                if getattr(route, "name", None) not in ("unknown_api_route", "frontend")
            )
        )
        if allowed:
            raise ApiError(
                405,
                "METHOD_NOT_ALLOWED",
                f"{request.method} is not allowed on {path}; use {', '.join(allowed)}",
                headers={"Allow": ", ".join(allowed)},
            )
        raise ApiError(404, "NOT_FOUND", f"there is no API endpoint {path}")

    if dist is not None and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


__all__ = ["create_app"]
