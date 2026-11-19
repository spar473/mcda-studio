"""Keep two reviewed model outputs separate and explicitly select one compatible target."""

from collections import Counter
from typing import Any, Literal

from pydantic import Field

from mcda_studio.domain.common import Issue
from mcda_studio.domain.errors import (
    McdaError,
    ModelEditError,
    StaleRevisionError,
    ValidationFailed,
)
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.model_comparison import ModelComparison, ModelOutputSpec, ModelScope
from mcda_studio.domain.project import Project
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.methods.formulas import FormulaError, parse
from mcda_studio.services import derived_service as derived
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services.questions_service import Question


class ModelOutputSnapshot(SidecarModel):
    status: Literal["completed", "unavailable"]
    run: checks.ModelOutputRun | None
    reason: str
    issues: list[Issue] = Field(default_factory=list)


class ModelComparisonInspection(SidecarModel):
    comparison: ModelComparison
    current_fingerprint: str
    stale: bool
    left: ModelOutputSnapshot
    right: ModelOutputSnapshot
    comparable: bool
    questions: list[Question]
    review_digest: str
    limitations: list[str]


class ModelTargetSelection(SidecarModel):
    side: Literal["left", "right"]
    alternative_id: str
    criterion_id: str
    target_scope: ModelScope
    review: Review


class ModelComparisonCompilation(SidecarModel):
    artifact_kind: Literal["model_comparison_compilation"] = "model_comparison_compilation"
    version: Literal[1] = 1
    source_project: Project
    inspection: ModelComparisonInspection
    selection: ModelTargetSelection
    calculation: derived.DerivedCompilation
    digest: str


def comparison_digest(comparison: ModelComparison) -> str:
    return derived._digest(comparison.model_dump(mode="json", exclude={"digest"}))


def known_scope(scope: ModelScope) -> bool:
    return all(
        value is not None and value.strip().casefold() not in {"", "unknown", "unspecified"}
        for value in scope.model_dump().values()
    )


def validate_segments(specification: ModelOutputSpec) -> None:
    aggregation = specification.aggregation
    if aggregation is None:
        return
    checks.accepted(
        aggregation.review,
        "MODEL_SEGMENT_REVIEW",
        "review population definitions and overlap explicitly",
    )
    quantities = {f.id: f for f in specification.model.formulas}
    ids = [s.formula_id for s in aggregation.segments]
    if len(ids) != len(set(ids)) or any(id not in quantities for id in ids):
        checks.fail("MODEL_SEGMENT_IDS", "segments need unique known formula IDs")
    if specification.formula_id not in quantities:
        checks.fail("MODEL_OUTPUT_ID", "select an existing formula output")
    output = quantities[specification.formula_id]
    if any(quantities[id].unit != output.unit for id in ids):
        checks.fail(
            "MODEL_SEGMENT_UNITS", "convert segment outputs explicitly to the total's exact unit"
        )
    used: set[str] = set()
    active: set[str] = set()

    def visit(id: str) -> None:
        if id in active:
            checks.fail("MODEL_SEGMENT_CYCLE", "segment dependencies contain a cycle")
        if id in used:
            return
        active.add(id)
        if id in quantities:
            from mcda_studio.services.factor_uncertainty_service import _names

            for child in _names(parse(quantities[id].expression)):
                visit(child)
        used.add(id)
        active.remove(id)

    visit(output.id)
    if not set(ids) <= used:
        checks.fail(
            "MODEL_SEGMENT_DEPENDENCIES", "the total must actually use every declared segment"
        )
    keys = [s.population_key for s in aggregation.segments]
    overlapping = len(set(keys)) != len(keys) or not aggregation.disjoint_populations
    if overlapping:
        if (
            aggregation.disjoint_populations
            or aggregation.overlap_model_formula_id != output.id
            or not aggregation.overlap_quantity_ids
            or not aggregation.rationale.strip()
            or not set(aggregation.overlap_quantity_ids) <= used - set(ids) - {output.id}
        ):
            checks.fail(
                "MODEL_SEGMENT_OVERLAP",
                "overlapping populations need an explicit used and reviewed overlap model",
            )
    else:
        # A plain sum declares its exact components; no inferred population independence.
        import ast

        def terms(node: ast.AST, sign: int = 1) -> Counter[str]:
            if isinstance(node, ast.Name):
                return Counter({node.id: sign})
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub):
                result = terms(node.left, sign)
                result.update(terms(node.right, -sign if isinstance(node.op, ast.Sub) else sign))
                return result
            checks.fail(
                "MODEL_SEGMENT_SUM", "declare a direct sum of the reviewed disjoint segments"
            )

        if terms(parse(output.expression).body) != Counter(ids):
            checks.fail("MODEL_SEGMENT_SUM", "the declared sum and segment list must agree exactly")


def _snapshot(project: Project, specification: ModelOutputSpec) -> ModelOutputSnapshot:
    try:
        validate_segments(specification)
        result = checks.run_output(project, specification)
    except FormulaError as exc:
        return ModelOutputSnapshot(status="unavailable", run=None, reason=f"{exc.code}: {exc}")
    except McdaError as exc:
        return ModelOutputSnapshot(
            status="unavailable",
            run=None,
            reason=str(exc),
            issues=exc.report.issues if isinstance(exc, ValidationFailed) else [],
        )
    return ModelOutputSnapshot(status="completed", run=result, reason="")


def inspect(project: Project, comparison: ModelComparison) -> ModelComparisonInspection:
    if comparison.digest != comparison_digest(comparison):
        raise ModelEditError("MODEL_COMPARISON_CHANGED: comparison digest does not match")
    stale = comparison.project_fingerprint != project.fingerprint()
    left, right = _snapshot(project, comparison.left), _snapshot(project, comparison.right)
    comparable = (
        known_scope(comparison.left.scope)
        and comparison.left.scope == comparison.right.scope
        and left.run is not None
        and right.run is not None
        and left.run.unit == right.run.unit == comparison.left.scope.unit
    )
    questions = [
        Question(
            group="evidence_quality",
            code="MODEL_DISAGREEMENT" if comparable else "MODEL_SCOPE_INCOMPARABLE",
            question="Which assumptions explain these model estimates?"
            if comparable
            else "Which reviewed scope makes these model outputs comparable?",
            why=(
                "Two distinct model declarations remain side by side, including "
                "when their ranges overlap."
            )
            if comparable
            else (
                "Unknown or different scope, units or unavailable outputs prevent a "
                "numeric comparison."
            ),
            evidence=(
                "Open Calculated measurements → Model comparisons; review both "
                "exact inputs/runs. Never average the models."
            ),
        )
    ]
    if comparison.review is None or comparison.review.status != "accepted":
        questions.append(
            Question(
                group="evidence_quality",
                code="MODEL_COMPARISON_REVIEW",
                question="Has an analyst reviewed both model declarations and their limitations?",
                why=(
                    "Model comparison review is separate from accepting a factor or "
                    "its distribution."
                ),
                evidence=(
                    "Review the scopes, source classifications, range meanings and "
                    "model differences."
                ),
            )
        )
    for side, snapshot in (("left", left), ("right", right)):
        if snapshot.status == "unavailable":
            questions.append(
                Question(
                    group="blocking",
                    code="MODEL_OUTPUT_UNAVAILABLE",
                    question=f"What blocks the {side} model output?",
                    why=snapshot.reason,
                    evidence=(
                        "Correct or review the affected inputs; missing values never become zero."
                    ),
                )
            )
    if stale:
        questions.append(
            Question(
                group="evidence_quality",
                code="MODEL_COMPARISON_STALE",
                question="Which project revision do these models describe?",
                why="Comparison binding differs from the open project.",
                evidence="Inspect/export historically; do not rebind a reviewed comparison.",
            )
        )
    body = {
        "comparison": comparison.digest,
        "project": project.fingerprint(),
        "left": left.model_dump(mode="json"),
        "right": right.model_dump(mode="json"),
    }
    return ModelComparisonInspection(
        comparison=comparison.model_copy(deep=True),
        current_fingerprint=project.fingerprint(),
        stale=stale,
        left=left,
        right=right,
        comparable=comparable,
        questions=questions,
        review_digest=derived._digest(body),
        limitations=[
            (
                "A range describes its declared kind; source bounds, supports and "
                "sampled central ranges are not interchangeable."
            ),
            (
                "Numeric overlap does not resolve a model disagreement, and no "
                "average or materiality threshold is calculated."
            ),
            (
                "Scope, population partition and reviewer identities are local "
                "assertions, not independent factual validation."
            ),
        ],
    )


def compile_selection(
    project: Project,
    comparison: ModelComparison,
    selection: ModelTargetSelection,
    expected_review_digest: str,
) -> ModelComparisonCompilation:
    current = inspect(project, comparison)
    if current.stale or current.review_digest != expected_review_digest:
        raise StaleRevisionError(
            "Model selection acknowledgement changed; inspect both models again"
        )
    checks.accepted(
        comparison.review,
        "MODEL_COMPARISON_REVIEW",
        "review the comparison before choosing a target",
    )
    checks.accepted(
        selection.review, "MODEL_TARGET_REVIEW", "explicitly review the selected output and target"
    )
    if not selection.review.note.strip():
        checks.fail(
            "MODEL_TARGET_RATIONALE", "record why this reviewed output supplies the criterion"
        )
    specification = comparison.left if selection.side == "left" else comparison.right
    snapshot = current.left if selection.side == "left" else current.right
    if snapshot.run is None:
        checks.fail("MODEL_TARGET_UNAVAILABLE", "the selected model output is unavailable")
    if not known_scope(selection.target_scope) or selection.target_scope != specification.scope:
        checks.fail(
            "MODEL_TARGET_SCOPE",
            "the target needs the selected output's exact known reviewed scope",
        )
    if selection.target_scope.unit != snapshot.run.unit:
        checks.fail("MODEL_TARGET_UNIT", "target scope and formula unit must match exactly")
    model = snapshot.run.scoped_model.model_copy(deep=True)
    selected = next(f for f in model.formulas if f.id == specification.formula_id)
    selected.alternative_id, selected.criterion_id = (
        selection.alternative_id,
        selection.criterion_id,
    )
    selected.review = selection.review.model_copy(deep=True)
    preview = derived.preview(project, model)
    calculation = derived.compilation_bundle(project, model, preview.review_digest)
    result = ModelComparisonCompilation(
        source_project=project.model_copy(deep=True),
        inspection=current,
        selection=selection.model_copy(deep=True),
        calculation=calculation,
        digest="",
    )
    result.digest = derived._digest(result.model_dump(mode="json", exclude={"digest"}))
    return result


def verify(bundle: ModelComparisonCompilation) -> ModelComparisonCompilation:
    if bundle.digest != derived._digest(bundle.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("MODEL_COMPARISON_BUNDLE_CHANGED: digest does not match")
    rebuilt = compile_selection(
        bundle.source_project,
        bundle.inspection.comparison,
        bundle.selection,
        bundle.inspection.review_digest,
    )
    if rebuilt != bundle:
        raise ModelEditError("MODEL_COMPARISON_BUNDLE_MISMATCH: selection does not reproduce")
    return bundle


def review(
    project: Project, comparison: ModelComparison, decision: Review, expected_review_digest: str
) -> ModelComparisonInspection:
    current = inspect(project, comparison)
    if current.stale or current.review_digest != expected_review_digest:
        raise StaleRevisionError(
            "MODEL_REVIEW_STALE: inspect this exact project/model revision again"
        )
    if not decision.reviewer.strip() or not decision.note.strip():
        checks.fail("MODEL_REVIEW_DETAILS", "record a reviewer and rationale for the comparison")
    revised = comparison.model_copy(deep=True)
    revised.review = decision.model_copy(deep=True)
    revised.digest = comparison_digest(revised)
    return inspect(project, revised)


def review_input(
    project: Project,
    comparison: ModelComparison,
    side: Literal["left", "right"],
    kind: Literal[
        "source", "formula", "distribution", "group", "checks", "interval", "aggregation"
    ],
    id: str,
    decision: Review,
    expected_review_digest: str,
) -> ModelComparisonInspection:
    current = inspect(project, comparison)
    if current.stale or current.review_digest != expected_review_digest:
        raise StaleRevisionError("MODEL_REVIEW_STALE: inspect this exact model revision again")
    if not decision.reviewer.strip() or not decision.note.strip():
        checks.fail(
            "MODEL_REVIEW_DETAILS", "record a reviewer and rationale for the displayed input"
        )
    revised = comparison.model_copy(deep=True)
    revised.left = comparison.left.model_copy(deep=True)
    revised.right = comparison.right.model_copy(deep=True)
    specification = revised.left if side == "left" else revised.right
    entries: list[Any] = []
    if kind in {"source", "formula"}:
        entries = specification.model.sources if kind == "source" else specification.model.formulas
    elif kind in {"distribution", "group"} and specification.uncertainty:
        entries = (
            specification.uncertainty.distributions
            if kind == "distribution"
            else specification.uncertainty.groups
        )
    elif kind == "checks" and specification.checks:
        entries = [specification.checks]
    elif kind == "interval" and hasattr(specification.range, "intervals"):
        entries = specification.range.intervals
    elif kind == "aggregation" and specification.aggregation:
        entries = [specification.aggregation]

    def identifier(entry: object) -> str:
        return str(getattr(entry, "id", getattr(entry, "factor_id", kind)))

    entry = next((entry for entry in entries if identifier(entry) == id), None)
    if entry is None:
        checks.fail("MODEL_REVIEW_INPUT", "select an existing input from the displayed declaration")
    if decision.status == "corrected" and kind != "source":
        checks.fail("MODEL_REVIEW_INPUT", "edit a new declaration to correct this input")
    entry.review = decision.model_copy(deep=True)
    if kind in {"source", "formula"}:
        # A newly reviewed deterministic model requires separate uncertainty and check reviews.
        model_digest = derived._digest(specification.model.model_dump(mode="json"))
        if specification.uncertainty:
            specification.uncertainty.model_digest = model_digest
            for distribution in specification.uncertainty.distributions:
                distribution.review = None
            for group in specification.uncertainty.groups:
                group.review = None
        if specification.checks:
            specification.checks.model_digest = model_digest
            specification.checks.review = None
    if specification.checks:
        specification.checks.digest = checks.checks_digest(specification.checks)
    revised.review = None
    revised.digest = comparison_digest(revised)
    return inspect(project, revised)
