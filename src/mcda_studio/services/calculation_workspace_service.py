"""Replay, inspect and extend calculation workspaces; no project, library or file writes.

Every event is replayed from the original snapshot; applying reuses the compilation gate, so an
applied project is byte-identical to the separate copy compilation would produce."""

import ast
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NoReturn

from pydantic import ValidationError

from mcda_studio.domain.calculation_workspace import (
    ApplyCalculation,
    CalculationEvent,
    CalculationWorkspace,
    DefineFormula,
    DefineSource,
    DefineUnit,
    ProposedEvent,
    Rebind,
    RemoveEntry,
    ReviewEntry,
)
from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.project import Project
from mcda_studio.domain.validation import ValidationReport, validate_structure
from mcda_studio.methods.formulas import FormulaError, parse
from mcda_studio.services import derived_service as derived

MAX_EVENTS = 2000


class FactorUse(DomainModel):
    """Which formulas and target alternatives depend on a factor, whatever its review state."""

    factor_id: str
    formula_ids: list[str]
    alternative_ids: list[str]
    shared: bool


class FormulaCheck(DomainModel):
    """The formula evaluated as if it alone were accepted; shown before its review."""

    formula_id: str
    references: list[str]
    status: Literal["calculates", "error"]
    value: float | None
    dimension: dict[str, int] | None
    issue: Issue | None
    explanation: str


class TargetChange(DomainModel):
    formula_id: str
    alternative_id: str
    criterion_id: str
    before: Measurement | None
    after: float
    changed: bool


class CalculationInspection(DomainModel):
    workspace: CalculationWorkspace
    model: DerivedModel
    preview: derived.DerivedPreview
    relationship: Literal["bound", "earlier", "different"]
    # The bound revisions in order: the start, then each apply or rebind.
    bindings: list[str]
    factor_uses: list[FactorUse]
    checks: list[FormulaCheck]
    changes: list[TargetChange]
    applicable: bool
    workspace_exportable: bool


class Assignment(DomainModel):
    alternative_id: str
    criterion_id: str
    value: float


class CalculationApplication(DomainModel):
    """A candidate: the editor applies the assignments as one edit, then confirms it."""

    inspection: CalculationInspection
    assignments: list[Assignment]
    project_fingerprint: str
    bundle: derived.DerivedCompilation


@dataclass
class _State:
    model: DerivedModel
    project: Project | None
    bindings: list[str]


def workspace_digest(workspace: CalculationWorkspace) -> str:
    return derived._digest(workspace.model_dump(mode="json", exclude={"digest"}))


def _refuse(index: int, code: str, message: str) -> NoReturn:
    raise ModelEditError(f"{code}: event {index}: {message}")


def _replace[T: (SourceFactor, DerivedFormula)](items: list[T], item: T) -> list[T]:
    """A redefinition keeps the entry's position, so formula order (and compilation) is stable."""
    if any(x.id == item.id for x in items):
        return [item if x.id == item.id else x for x in items]
    return items + [item]


def _step(
    model: DerivedModel, project: Project, event: CalculationEvent, index: int
) -> tuple[DerivedModel, Project]:
    m = model.model_copy(deep=True)
    if isinstance(event, DefineUnit):
        if event.unit == "1":
            _refuse(index, "CALCULATION_UNIT_RESERVED", "unit '1' is dimensionless")
        if event.unit in m.units:
            _refuse(index, "CALCULATION_UNIT_EXISTS", f"unit {event.unit!r} is already defined")
        m.units = {**m.units, event.unit: dict(event.dimension)}
    elif isinstance(event, DefineSource | DefineFormula):
        entry = event.factor if isinstance(event, DefineSource) else event.formula
        others = m.formulas if isinstance(event, DefineSource) else m.sources
        if entry.review is not None:
            _refuse(index, "CALCULATION_DEFINITION_REVIEWED", "review a definition separately")
        if any(x.id == entry.id for x in others):
            _refuse(index, "CALCULATION_ID_IN_USE", f"{entry.id!r} already names another entry")
        if isinstance(event, DefineSource):
            m.sources = _replace(m.sources, event.factor)
        else:
            m.formulas = _replace(m.formulas, event.formula)
    elif isinstance(event, ReviewEntry):
        matches = [
            x for x in (m.sources if event.entry == "source" else m.formulas) if x.id == event.id
        ]
        if len(matches) != 1:
            _refuse(
                index, "CALCULATION_REVIEW_ENTRY", f"review needs one {event.entry} {event.id!r}"
            )
        review = event.review
        if event.entry == "formula" and review.status == "corrected":
            _refuse(index, "CALCULATION_FORMULA_CORRECTION", "redefine a formula to change it")
        if review.status == "corrected" and isinstance(review.corrected_value, str):
            _refuse(index, "CALCULATION_CORRECTION_VALUE", "a factor correction must be a number")
        matches[0].review = review.model_copy(deep=True)
    elif isinstance(event, RemoveEntry):
        if event.entry == "source":
            kept_sources = [x for x in m.sources if x.id != event.id]
            if len(kept_sources) == len(m.sources):
                _refuse(index, "CALCULATION_REMOVE_ENTRY", f"no factor {event.id!r}")
            m.sources = kept_sources
        else:
            kept_formulas = [x for x in m.formulas if x.id != event.id]
            if len(kept_formulas) == len(m.formulas):
                _refuse(index, "CALCULATION_REMOVE_ENTRY", f"no formula {event.id!r}")
            m.formulas = kept_formulas
    elif isinstance(event, Rebind):
        if event.project.id != project.id:
            _refuse(index, "CALCULATION_REBIND_PROJECT", "a rebind keeps the same project ID")
        fingerprint = event.project.fingerprint()
        if fingerprint == m.project_fingerprint:
            _refuse(index, "CALCULATION_REBIND_SAME", "already bound to this revision")
        project = event.project.model_copy(deep=True)
        m.project_fingerprint = fingerprint
    else:
        report = derived.preview(project, m)
        if report.review_digest != event.review_digest:
            _refuse(index, "CALCULATION_APPLY_DIGEST", "the applied review does not reproduce")
        if any(i.severity is Severity.ERROR for i in report.issues):
            _refuse(index, "CALCULATION_APPLY_INVALID", "the applied calculation has errors")
        if not any(c.changed for c in _changes(report)):
            _refuse(index, "CALCULATION_APPLY_UNCHANGED", "the application changes no value")
        applied = derived.compile_copy(project, m, event.review_digest)
        if applied.fingerprint() != event.project_fingerprint:
            _refuse(index, "CALCULATION_APPLY_RESULT", "the applied project does not reproduce")
        project = applied
        m.project_fingerprint = event.project_fingerprint
    return m, project


def _replay(workspace: CalculationWorkspace) -> _State:
    if workspace.digest != workspace_digest(workspace):
        raise ModelEditError("CALCULATION_HISTORY_CHANGED: workspace digest does not match")
    project = workspace.source_project.model_copy(deep=True)
    if project.fingerprint() != workspace.original_model.project_fingerprint:
        raise ModelEditError("CALCULATION_HISTORY_PROJECT: original model and project differ")
    model = workspace.original_model.model_copy(deep=True)
    bindings = [model.project_fingerprint]
    for index, event in enumerate(workspace.events):
        try:
            model, project = _step(model, project, event, index)
        except ValidationError as exc:
            _refuse(index, "CALCULATION_EVENT_INVALID", exc.errors()[0]["msg"])
        if model.project_fingerprint != bindings[-1]:
            bindings.append(model.project_fingerprint)
    return _State(model, project, bindings)


def _changes(report: derived.DerivedPreview) -> list[TargetChange]:
    return [
        TargetChange(
            formula_id=c.id,
            alternative_id=c.alternative_id,
            criterion_id=c.criterion_id,
            before=c.before,
            after=c.value,
            changed=c.before != c.value,
        )
        for c in report.calculations
        if c.alternative_id is not None and c.criterion_id is not None
    ]


def references(expression: str) -> list[str]:
    """Names an expression refers to, from the bounded parser; empty if it does not parse."""
    try:
        tree = parse(expression)
    except FormulaError:
        return []
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called})


def _uses(model: DerivedModel) -> list[FactorUse]:
    """Static dependents, so a pending or rejected factor still shows what it would affect."""
    refs = {f.id: references(f.expression) for f in model.formulas}
    sources = {s.id for s in model.sources}

    def fundamentals(formula_id: str, seen: frozenset[str]) -> set[str]:
        found: set[str] = set()
        for name in refs[formula_id]:
            if name in sources:
                found.add(name)
            elif name in refs and name not in seen:
                found |= fundamentals(name, seen | {name})
        return found

    closure = {f.id: fundamentals(f.id, frozenset({f.id})) for f in model.formulas}
    uses = []
    for source in model.sources:
        dependents = [f for f in model.formulas if source.id in closure[f.id]]
        alternatives = sorted({f.alternative_id for f in dependents if f.alternative_id})
        uses.append(
            FactorUse(
                factor_id=source.id,
                formula_ids=[f.id for f in dependents],
                alternative_ids=alternatives,
                shared=len(alternatives) > 1,
            )
        )
    return uses


def _dimension_text(dimension: dict[str, int]) -> str:
    if not dimension:
        return "dimensionless"
    return " × ".join(
        name if power == 1 else f"{name}^{power}" for name, power in sorted(dimension.items())
    )


def _checks(project: Project, model: DerivedModel) -> list[FormulaCheck]:
    checks = []
    structure = list(validate_structure(project).issues)  # once, not once per formula
    for formula in model.formulas:
        run = derived.trial(project, model, formula.id, structure)
        path = f"formulas[{formula.id}]"
        calculation = next((c for c in run.calculations if c.id == formula.id), None)
        issue = next(
            (i for i in run.issues if i.severity is Severity.ERROR and i.path == path), None
        ) or next((i for i in run.issues if i.severity is Severity.ERROR), None)
        if calculation is not None:
            explanation = (
                f"Calculates {calculation.value:.12g} {formula.unit}; its dimensions "
                f"({_dimension_text(calculation.dimension)}) match the declared unit."
            )
        else:
            assert issue is not None
            dims = run.dimensions.get(path, {})
            where = run.failed_in.get(path)
            prefix = f"In {where}: " if where and where != formula.id else ""
            if issue.code == "DERIVED_OUTPUT_DIMENSION":
                explanation = (
                    f"{prefix}the expression gives {_dimension_text(dims['calculated'])}, but "
                    f"the declared unit is {_dimension_text(dims['declared'])}."
                )
            elif issue.code == "FORMULA_DIMENSION":
                explanation = (
                    f"{prefix}only quantities with the same dimensions can be added, "
                    f"subtracted or compared: {_dimension_text(dims['left'])} and "
                    f"{_dimension_text(dims['right'])}."
                )
            elif issue.code in derived._INPUT_CODES:
                explanation = f"Accept its inputs first: {issue.message}."
            else:
                explanation = f"{prefix}{issue.message}."
        explanation = explanation[:1].upper() + explanation[1:]
        checks.append(
            FormulaCheck(
                formula_id=formula.id,
                references=references(formula.expression),
                status="calculates" if calculation is not None else "error",
                value=None if calculation is None else calculation.value,
                dimension=None if calculation is None else calculation.dimension,
                issue=None if calculation is not None else issue,
                explanation=explanation,
            )
        )
    return checks


def inspect(
    project: Project, document: DerivedModel | CalculationWorkspace
) -> CalculationInspection:
    current = project.fingerprint()
    if isinstance(document, CalculationWorkspace):
        workspace = document.model_copy(deep=True)
        state = _replay(workspace)
        exportable = True
    else:
        model = document.model_copy(deep=True)
        workspace = CalculationWorkspace(
            source_project=project.model_copy(deep=True), original_model=model, digest=""
        )
        workspace.digest = workspace_digest(workspace)
        # A raw model for another revision has no snapshot of that revision: read it only.
        exportable = model.project_fingerprint == current
        state = _State(model, project if exportable else None, [model.project_fingerprint])
    report = derived.preview(project, state.model)
    relationship: Literal["bound", "earlier", "different"] = (
        "bound"
        if current == state.bindings[-1]
        else "earlier"
        if current in state.bindings
        else "different"
    )
    bound = relationship == "bound" and exportable
    changes = _changes(report)
    return CalculationInspection(
        workspace=workspace,
        model=state.model,
        preview=report,
        relationship=relationship,
        bindings=state.bindings,
        factor_uses=_uses(state.model),
        checks=_checks(project, state.model) if bound else [],
        changes=changes,
        applicable=bound
        and not any(i.severity is Severity.ERROR for i in report.issues)
        and any(c.changed for c in changes),
        workspace_exportable=exportable,
    )


def _people(event: ProposedEvent) -> list[str]:
    if isinstance(event, ReviewEntry):
        return [event.review.reviewer]
    if isinstance(event, DefineSource):
        return [event.factor.origin.proposed_by]
    if isinstance(event, DefineFormula):
        return [event.formula.origin.proposed_by]
    return [event.recorded_by]


def _current(
    project: Project, workspace: CalculationWorkspace, expected_review_digest: str
) -> CalculationInspection:
    # Replay refuses a workspace started from a model for another revision (no snapshot of it).
    current = inspect(project, workspace)
    if current.preview.review_digest != expected_review_digest:
        raise StaleRevisionError("Calculation preview changed; inspect it again before editing.")
    if len(workspace.events) >= MAX_EVENTS:
        raise ModelEditError("CALCULATION_HISTORY_LIMIT: workspace already has 2000 events")
    return current


def _extend(workspace: CalculationWorkspace, event: CalculationEvent) -> CalculationWorkspace:
    candidate = workspace.model_copy(deep=True)
    candidate.events.append(event.model_copy(deep=True))
    candidate.digest = workspace_digest(candidate)
    return candidate


def propose(
    project: Project,
    workspace: CalculationWorkspace,
    event: ProposedEvent,
    expected_review_digest: str,
) -> CalculationInspection:
    """Return a candidate for explicit confirmation; the input workspace is not changed."""
    current = _current(project, workspace, expected_review_digest)
    if any(not person.strip() for person in _people(event)):
        raise ModelEditError("CALCULATION_PERSON: name the person recording this change")
    if isinstance(event, Rebind):
        if current.relationship == "bound":
            raise ModelEditError("CALCULATION_REBIND_SAME: already bound to this revision")
        if event.project.fingerprint() != project.fingerprint():
            raise ModelEditError("CALCULATION_REBIND_PROJECT: rebind to the open project only")
    elif current.relationship != "bound":
        raise StaleRevisionError("Calculation workspace does not match this project revision.")
    if isinstance(event, ReviewEntry) and event.review.status != "rejected":
        if event.entry == "source":
            factor = next((s for s in current.model.sources if s.id == event.id), None)
            corrected = event.review.status == "corrected"
            value = event.review.corrected_value if corrected else factor and factor.value
            if factor is not None and value is None:
                raise ModelEditError(
                    f"CALCULATION_ACCEPT_MISSING: factor {event.id!r} has no value to accept"
                )
        else:
            check = next((c for c in current.checks if c.formula_id == event.id), None)
            if check is not None and check.status != "calculates":
                raise ModelEditError(
                    f"CALCULATION_ACCEPT_INVALID: formula {event.id!r} does not calculate. "
                    + check.explanation
                )
    return inspect(project, _extend(workspace, event))


def apply(
    project: Project,
    workspace: CalculationWorkspace,
    expected_review_digest: str,
    recorded_by: str,
    recorded_at: datetime,
) -> CalculationApplication:
    """Recompile the acknowledged preview and return the edit plus its candidate history."""
    current = _current(project, workspace, expected_review_digest)
    if not recorded_by.strip():
        raise ModelEditError("CALCULATION_PERSON: name the person applying the calculation")
    if current.relationship != "bound":
        raise StaleRevisionError("Calculation workspace does not match this project revision.")
    errors = [i for i in current.preview.issues if i.severity is Severity.ERROR]
    if errors:
        raise ValidationFailed(ValidationReport(issues=errors))
    if not any(c.changed for c in current.changes):
        raise ModelEditError(
            "CALCULATION_APPLY_UNCHANGED: every calculated value already equals its measurement"
        )
    bundle = derived.compilation_bundle(project, current.model, expected_review_digest)
    event = ApplyCalculation(
        review_digest=expected_review_digest,
        recorded_by=recorded_by,
        recorded_at=recorded_at,
        project_fingerprint=bundle.compiled_fingerprint,
    )
    return CalculationApplication(
        inspection=inspect(bundle.project, _extend(workspace, event)),
        assignments=[
            Assignment(alternative_id=c.alternative_id, criterion_id=c.criterion_id, value=c.after)
            for c in current.changes
        ],
        project_fingerprint=bundle.compiled_fingerprint,
        bundle=bundle,
    )
