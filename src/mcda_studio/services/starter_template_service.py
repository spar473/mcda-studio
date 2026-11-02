"""Hash-checked local manifests and explicit draft creation, independent of template names."""

import hashlib
import io
import json
import uuid
import zipfile
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.external_proposals import ExternalProposals
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.model_comparison import ModelChecks, ModelComparison
from mcda_studio.domain.project import SCHEMA_VERSION, Project
from mcda_studio.domain.starter_templates import (
    StarterArtifactData,
    StarterInstantiationRequest,
    StarterLineageReceipt,
    StarterMaterialization,
    StarterTemplate,
)
from mcda_studio.runtime import asset_directory
from mcda_studio.services import derived_service as derived
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import proposal_service as proposals
from mcda_studio.services.proposal_import_service import read_local, strict_json

# Formats, not template identities, determine validation and draft reset behaviour.
FORMATS: dict[str, type[BaseModel]] = {
    "project": Project,
    "derived_model": DerivedModel,
    "factor_uncertainty": FactorUncertaintyModel,
    "evidence_dossier": EvidenceDossier,
    "external_proposals": ExternalProposals,
    "model_checks": ModelChecks,
    "model_comparison": ModelComparison,
    "model_output_run": checks.ModelOutputRun,
    "model_comparison_compilation": comparisons.ModelComparisonCompilation,
}
SNAPSHOTS = {"model_output_run", "model_comparison_compilation"}
WARNING = "Illustrative starter inputs require your review; carried human acceptances were cleared."


def template_digest(template: StarterTemplate) -> str:
    return derived._digest(template.model_dump(mode="json", exclude={"digest"}))


def _local(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in name
        or not relative.parts
        or name != str(relative)
    ):
        raise ModelEditError("STARTER_PATH: artifact paths must be canonical relative local paths")
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ModelEditError("STARTER_PATH: artifacts cannot escape their manifest directory")
    return target


def _load(root: Path, manifest: Path) -> tuple[StarterTemplate, dict[str, StarterArtifactData]]:
    if not manifest.resolve().is_relative_to(root.resolve()):
        raise ModelEditError("STARTER_PATH: manifest cannot escape the local catalog")
    template = StarterTemplate.model_validate_json(read_local(manifest))
    if template.digest != template_digest(template):
        raise ModelEditError("STARTER_DIGEST: manifest digest does not match")
    ids = [a.id for a in template.artifacts]
    if len(ids) != len(set(ids)) or sum(a.kind == "project" for a in template.artifacts) != 1:
        raise ModelEditError("STARTER_ARTIFACTS: unique IDs and exactly one project are required")
    loaded: dict[str, StarterArtifactData] = {}
    total = 0
    for artifact in template.artifacts:
        path = _local(manifest.parent, artifact.path)
        text = read_local(path)
        total += len(text.encode())
        if total > 32_000_000:
            raise ModelEditError("STARTER_LIMIT: at most 32 MB of local materials")
        if hashlib.sha256(text.encode()).hexdigest() != artifact.sha256:
            raise ModelEditError(f"STARTER_ARTIFACT_CHANGED: hash mismatch for {artifact.id}")
        model_type = FORMATS.get(artifact.kind)
        if model_type is None:
            raise ModelEditError(f"STARTER_KIND: unsupported artifact kind {artifact.kind}")
        raw = strict_json(text)
        version = raw.get("schema_version", raw.get("version", raw.get("workspace_version")))
        if type(version) is not int or version != artifact.schema_version:
            raise ModelEditError("STARTER_VERSION: artifact version differs from its manifest")
        if artifact.kind == "project" and not 1 <= version <= SCHEMA_VERSION:
            raise ModelEditError("STARTER_VERSION: unsupported project version")
        if artifact.kind in SNAPSHOTS and artifact.reset_policy != "omit":
            raise ModelEditError(
                "STARTER_RESET: historical snapshots must be omitted from fresh copies"
            )
        parsed = model_type.model_validate_json(text)
        loaded[artifact.id] = StarterArtifactData(
            kind=artifact.kind,
            schema_version=artifact.schema_version,
            label=artifact.label,
            value=parsed.model_dump(mode="json"),
        )
    project = Project.model_validate(next(a.value for a in loaded.values() if a.kind == "project"))
    for artifact in template.artifacts:
        data = loaded[artifact.id]
        if (
            data.kind != "project"
            and data.value.get("project_fingerprint", project.fingerprint())
            != project.fingerprint()
        ):
            raise ModelEditError("STARTER_BINDING: all inputs must belong to the manifest project")
        if artifact.for_model is not None:
            bound = loaded.get(artifact.for_model)
            if bound is None or bound.kind != "derived_model":
                raise ModelEditError("STARTER_BINDING: for_model must name a calculation model")
            if data.value.get("model_digest") != derived._digest(bound.value):
                raise ModelEditError("STARTER_BINDING: sidecar model digest differs")
    return template, loaded


def _catalog(root: Path) -> dict[str, tuple[StarterTemplate, dict[str, StarterArtifactData]]]:
    catalog = {}
    for manifest in sorted((root / "starter_templates").glob("*/manifest.json")):
        template, values = _load(root, manifest)
        if template.id in catalog:
            raise ModelEditError("STARTER_DUPLICATE: template IDs must be unique")
        catalog[template.id] = template, values
    return catalog


def list_templates(root: Path | None = None) -> list[StarterTemplate]:
    with ExitStack() as stack:
        directory = root or asset_directory("examples", None, stack)
        return [] if directory is None else [value[0] for value in _catalog(directory).values()]


def _clear_reviews(value: Any, path: str, cleared: list[str]) -> Any:
    if isinstance(value, list):
        return [_clear_reviews(v, f"{path}/{i}", cleared) for i, v in enumerate(value)]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            location = f"{path}/{key}"
            if key == "review":
                if item is not None:
                    cleared.append(location)
                out[key] = None
            else:
                out[key] = _clear_reviews(item, location, cleared)
        return out
    return value


def _model_draft(
    raw: dict[str, Any], fingerprint: str, path: str, cleared: list[str]
) -> dict[str, Any]:
    # A corrected deterministic value is a proposed input in the new draft, never an acceptance.
    raw = json.loads(json.dumps(raw))
    for source in raw["sources"]:
        review = source.get("review")
        if review and review["status"] == "corrected":
            source["value"] = review["corrected_value"]
    raw = _clear_reviews(raw, path, cleared)
    raw["project_fingerprint"] = fingerprint
    return raw


def _comparison_draft(
    raw: dict[str, Any], fingerprint: str, path: str, cleared: list[str]
) -> dict[str, Any]:
    raw = json.loads(json.dumps(raw))
    for side in ("left", "right"):
        raw[side]["model"] = _model_draft(
            raw[side]["model"], fingerprint, f"{path}/{side}/model", cleared
        )
    raw = _clear_reviews(raw, path, cleared)
    raw["project_fingerprint"] = fingerprint
    for side in ("left", "right"):
        spec = raw[side]
        digest = derived._digest(spec["model"])
        for field in ("uncertainty", "checks"):
            if spec[field] is not None:
                spec[field]["project_fingerprint"] = fingerprint
                spec[field]["model_digest"] = digest
        if spec["checks"] is not None:
            spec["checks"]["digest"] = checks.checks_digest(
                ModelChecks.model_validate_json(json.dumps(spec["checks"]))
            )
    result = ModelComparison.model_validate_json(json.dumps(raw))
    result.digest = comparisons.comparison_digest(result)
    return result.model_dump(mode="json")


def instantiate(
    request: StarterInstantiationRequest, root: Path | None = None
) -> StarterMaterialization:
    with ExitStack() as stack:
        directory = root or asset_directory("examples", None, stack)
        catalog = _catalog(directory) if directory else {}
    if request.template_id not in catalog:
        raise ModelEditError("STARTER_UNKNOWN: unknown local template")
    template, loaded = catalog[request.template_id]
    project_id = next(id for id, item in loaded.items() if item.kind == "project")
    original = Project.model_validate(loaded[project_id].value)
    project = original.model_copy(deep=True)
    optional = {a.id for a in template.artifacts if a.optional}
    if (
        len(request.optional_artifact_ids) != len(set(request.optional_artifact_ids))
        or not set(request.optional_artifact_ids) <= optional
    ):
        raise ModelEditError(
            "STARTER_OPTIONAL: select only declared optional artifact IDs, once each"
        )
    actual = request.model_copy(deep=True)
    cleared: list[str] = []
    omitted: list[str] = []
    if request.mode == "fresh":
        actual.project_id = request.project_id or uuid.uuid4().hex[:16]
        if actual.project_id == original.id:
            raise ModelEditError("STARTER_ID: a fresh project requires a new project ID")
        project.id = actual.project_id
        project.title = request.title.strip() or template.title
        project.description = f"{WARNING}\n{request.description}".strip()
        project.decision_maker = request.decision_maker
        cleared.extend(["project/description", "project/decision_maker"])
    elif any((request.title, request.description, request.decision_maker, request.project_id)):
        raise ModelEditError(
            "STARTER_WORKED: a worked example retains its exact project and provenance"
        )
    fingerprint = project.fingerprint()
    artifacts: dict[str, StarterArtifactData] = {}
    for descriptor in template.artifacts:
        if descriptor.kind == "project":
            continue
        if (descriptor.optional and descriptor.id not in request.optional_artifact_ids) or (
            request.mode == "fresh" and descriptor.reset_policy == "omit"
        ):
            omitted.append(descriptor.id)
            continue
        item = loaded[descriptor.id].model_copy(deep=True)
        if request.mode == "fresh":
            path = f"artifacts/{descriptor.id}"
            if item.kind == "derived_model":
                item.value = _model_draft(item.value, fingerprint, path, cleared)
            elif item.kind == "model_comparison":
                item.value = _comparison_draft(item.value, fingerprint, path, cleared)
            elif item.kind == "external_proposals":
                old = ExternalProposals.model_validate_json(json.dumps(item.value))
                intake = proposals.resolved_intake(old)
                raw = _clear_reviews(intake.model_dump(mode="json"), path + "/intake", cleared)
                raw["project_fingerprint"] = fingerprint
                if raw["human_dossier"] is not None:
                    raw["human_dossier"]["project_fingerprint"] = fingerprint
                from mcda_studio.domain.external_proposals import ProposalIntake

                item.value = proposals.start(
                    project, ProposalIntake.model_validate_json(json.dumps(raw))
                ).model_dump(mode="json")
                if old.reviews or old.registry_supplies:
                    cleared.extend([path + "/reviews", path + "/registry_supplies"])
            else:
                item.value = _clear_reviews(item.value, path, cleared)
                item.value["project_fingerprint"] = fingerprint
            artifacts[descriptor.id] = item
        else:
            artifacts[descriptor.id] = item
    # Bind new draft uncertainty/checks only after all draft calculation models exist.
    if request.mode == "fresh":
        for descriptor in template.artifacts:
            if descriptor.id not in artifacts or descriptor.for_model is None:
                continue
            if descriptor.for_model not in artifacts:
                raise ModelEditError("STARTER_OPTIONAL: selected sidecar requires its model")
            item = artifacts[descriptor.id]
            item.value["model_digest"] = derived._digest(artifacts[descriptor.for_model].value)
            if item.kind == "model_checks":
                item.value["digest"] = checks.checks_digest(
                    ModelChecks.model_validate_json(json.dumps(item.value))
                )
        for item in artifacts.values():
            item.value = (
                FORMATS[item.kind]
                .model_validate_json(json.dumps(item.value))
                .model_dump(mode="json")
            )
    receipt = StarterLineageReceipt(
        template_id=template.id,
        template_version=template.version,
        template_digest=template.digest,
        request=actual,
        original_project_fingerprint=original.fingerprint(),
        project_fingerprint=fingerprint,
        artifact_digests={id: derived._digest(a.value) for id, a in artifacts.items()},
        cleared_fields=sorted(set(cleared)),
        omitted_artifact_ids=sorted(omitted),
        limitations=[
            (
                "All carried values and identities are invented illustrative inputs, "
                "requiring local review."
            ),
            (
                "Lineage verifies local content and explicit resets, "
                "not factual accuracy or reviewer identity."
            ),
            (
                "Optional materials are unattached; selecting them does not create "
                "a criterion or measurement."
            ),
        ],
        digest="",
    )
    receipt.digest = derived._digest(receipt.model_dump(mode="json", exclude={"digest"}))
    result = StarterMaterialization(
        template=template, project=project, artifacts=artifacts, receipt=receipt, digest=""
    )
    result.digest = derived._digest(result.model_dump(mode="json", exclude={"digest"}))
    return result


def verify(materials: StarterMaterialization, root: Path | None = None) -> StarterMaterialization:
    # Reconstruct typed sidecars before hashing: a browser JSON round trip writes 1.0 as 1.
    # Numeric values are unchanged; canonical scalar types come from their declared formats.
    materials = materials.model_copy(deep=True)
    for item in materials.artifacts.values():
        model_type = FORMATS.get(item.kind)
        if model_type is None:
            raise ModelEditError("STARTER_KIND: unsupported artifact kind")
        item.value = model_type.model_validate_json(json.dumps(item.value)).model_dump(mode="json")
    if materials.digest != derived._digest(materials.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("STARTER_CHANGED: materialization digest differs")
    if instantiate(materials.receipt.request, root) != materials:
        raise ModelEditError(
            "STARTER_MISMATCH: materialization does not match its manifest and resets"
        )
    return materials


def archive(materials: StarterMaterialization, root: Path | None = None) -> bytes:
    verify(materials, root)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as output:
        files = {
            "project.json": materials.project.model_dump(mode="json"),
            "lineage.json": materials.receipt.model_dump(mode="json"),
            "materials.json": materials.model_dump(mode="json"),
            **{f"{id}.json": item.value for id, item in materials.artifacts.items()},
        }
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            output.writestr(
                info, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
    return stream.getvalue()
