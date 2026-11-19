"""Preview deterministic calculations and explicitly compile a new project copy."""

import hashlib
import json
import keyword
from collections import Counter
from typing import Literal

from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import ScaleType
from mcda_studio.domain.validation import ValidationReport, validate_structure
from mcda_studio.methods.formulas import FormulaError, Quantity, calculate, parse
from mcda_studio.services import project_service as ps


class Calculation(DomainModel):
    id: str
    expression: str
    value: float
    unit: str
    dimension: dict[str, int]
    dependencies: list[str]
    source_ids: list[str]
    alternative_id: str | None
    criterion_id: str | None
    before: Measurement | None


class DerivedPreview(DomainModel):
    project_fingerprint: str
    model_digest: str
    review_digest: str
    model: DerivedModel
    calculations: list[Calculation]
    issues: list[Issue]
    limitations: list[str]


class DerivedCompilation(DomainModel):
    """Reproducible static copy with the exact original assumptions and review context."""

    compilation_version: Literal[1] = 1
    source_project: Project
    preview: DerivedPreview
    project: Project
    compiled_fingerprint: str
    digest: str


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


#: Errors about a referenced input, attributed to that input rather than to the formula using it.
_INPUT_CODES = frozenset(
    {"DERIVED_UNREVIEWED_SOURCE", "DERIVED_MISSING_INPUT", "DERIVED_UNREVIEWED_FORMULA"}
)


class _Run(DomainModel):
    calculations: list[Calculation]
    issues: list[Issue]
    # Explanation details keyed by issue path; never digested or exported.
    dimensions: dict[str, dict[str, dict[str, int]]]
    failed_in: dict[str, str]


def preview(project: Project, model: DerivedModel) -> DerivedPreview:
    """The full input snapshot and dependency trace travel with every calculation."""
    run = _run(project, model)
    calculations, issues = run.calculations, run.issues
    model_body = model.model_dump(mode="json")
    body = {
        "project_fingerprint": project.fingerprint(),
        "model": model_body,
        "calculations": [c.model_dump(mode="json") for c in calculations],
        "issues": [i.model_dump(mode="json") for i in issues],
    }
    return DerivedPreview(
        project_fingerprint=project.fingerprint(),
        model_digest=_digest(model_body),
        review_digest=_digest(body),
        model=model.model_copy(deep=True),
        calculations=calculations,
        issues=issues,
        limitations=[
            "Deterministic calculation only; no distribution is inferred or propagated.",
            "Units have analyst-declared dimensions; no implicit scaling or conversion.",
            "Shared sources are evaluated once and traced; uncertain factors are unsupported.",
            "Compiling makes a static copy; retain this preview to preserve the formula trace.",
        ],
    )


def trial(
    project: Project, model: DerivedModel, formula_id: str, structure: list[Issue] | None = None
) -> _Run:
    """Evaluate as if this one formula were accepted, to check it before its review.

    Never compiled or digested: the preview above remains the only acceptance gate."""
    return _run(project, model, frozenset({formula_id}), structure)


def _run(
    project: Project,
    model: DerivedModel,
    assume_accepted: frozenset[str] = frozenset(),
    structure: list[Issue] | None = None,
) -> _Run:
    issues = list(validate_structure(project).issues if structure is None else structure)
    calculations: list[Calculation] = []
    explained: dict[str, dict[str, dict[str, int]]] = {}
    failed_in: dict[str, str] = {}

    def error(code: str, message: str, path: str = "") -> None:
        issues.append(Issue(severity=Severity.ERROR, code=code, message=message, path=path))

    if model.project_fingerprint != project.fingerprint():
        error("DERIVED_STALE_PROJECT", "calculation model does not match this project revision")
    names = [s.id for s in model.sources] + [f.id for f in model.formulas]
    for name, count in sorted(Counter(names).items()):
        if count > 1:
            error("DERIVED_DUPLICATE_ID", f"duplicate factor/formula id {name}")
        if keyword.iskeyword(name) or name in {"min", "max"}:
            error("DERIVED_RESERVED_ID", f"reserved expression name {name}")
    if model.units.get("1"):
        error("DERIVED_UNIT_DEFINITION", "unit '1' is dimensionless and cannot be redefined")
    if any(len(dimension) > 16 for dimension in model.units.values()):
        error("DERIVED_UNIT_LIMIT", "a unit may have at most 16 base dimensions")
    sources = {s.id: s for s in model.sources}
    formulas = {f.id: f for f in model.formulas}
    raw = project.performance_index()
    cache: dict[str, Quantity] = {}
    dependencies: dict[str, set[str]] = {}
    upstream: dict[str, set[str]] = {}
    active: list[str] = []

    def dimension(unit: str) -> dict[str, int]:
        if unit == "1":
            return {}
        if unit not in model.units:
            raise FormulaError("DERIVED_UNKNOWN_UNIT", f"unit {unit!r} needs explicit dimensions")
        return {key: exponent for key, exponent in model.units[unit].items() if exponent}

    def resolve(name: str) -> Quantity:
        if name in cache:
            return cache[name]
        if name in active:
            raise FormulaError(
                "DERIVED_CYCLE", "circular dependency: " + " -> ".join([*active, name])
            )
        if len(active) >= 64:
            raise FormulaError("DERIVED_DEPTH_LIMIT", "dependency depth exceeds 64")
        if name in sources:
            source = sources[name]
            review = source.review
            if review is None or review.status == "rejected":
                raise FormulaError(
                    "DERIVED_UNREVIEWED_SOURCE", f"factor {name!r} requires acceptance"
                )
            value = review.corrected_value if review.status == "corrected" else source.value
            if value is None or isinstance(value, str):
                raise FormulaError(
                    "DERIVED_MISSING_INPUT", f"factor {name!r} needs an accepted number"
                )
            result = Quantity(value, dimension(source.unit))
            upstream[name] = {name}
        elif name in formulas:
            formula = formulas[name]
            accepted = formula.review is not None and formula.review.status == "accepted"
            if not accepted and name not in assume_accepted:
                raise FormulaError(
                    "DERIVED_UNREVIEWED_FORMULA", f"formula {name!r} requires acceptance"
                )
            active.append(name)
            dependencies[name] = set()
            upstream[name] = set()

            def reference(key: str) -> Quantity:
                quantity = resolve(key)
                dependencies[name].add(key)
                upstream[name].update(upstream[key])
                return quantity

            try:
                result = calculate(parse(formula.expression), reference)
                if result.dimension != dimension(formula.unit):
                    raise FormulaError(
                        "DERIVED_OUTPUT_DIMENSION",
                        "calculated and declared dimensions differ",
                        {"calculated": result.dimension, "declared": dimension(formula.unit)},
                    )
            except FormulaError as exc:
                if exc.formula_id is None and exc.code not in _INPUT_CODES:
                    exc.formula_id = name
                raise
            finally:
                active.pop()
        else:
            raise FormulaError("DERIVED_UNKNOWN_INPUT", f"unknown input reference {name!r}")
        cache[name] = result
        return result

    if not any(i.severity is Severity.ERROR for i in issues):
        tree = project.tree()
        targets: set[tuple[str, str]] = set()
        for formula in model.formulas:
            path = f"formulas[{formula.id}]"
            try:
                quantity = resolve(formula.id)
                alt, criterion = formula.alternative_id, formula.criterion_id
                before = None
                if (alt is None) != (criterion is None):
                    raise FormulaError(
                        "DERIVED_TARGET", "measurement needs both alternative and criterion"
                    )
                if alt is not None and criterion is not None:
                    if (
                        alt not in project.alternative_ids()
                        or criterion not in tree
                        or not tree.is_leaf(criterion)
                    ):
                        raise FormulaError(
                            "DERIVED_TARGET", "target must be a known alternative and leaf"
                        )
                    if (alt, criterion) in targets:
                        raise FormulaError(
                            "DERIVED_DUPLICATE_TARGET",
                            "multiple formulas target the same measurement",
                        )
                    targets.add((alt, criterion))
                    scale = tree.node(criterion).scale
                    if scale is None or not scale.is_numeric or (scale.unit or "1") != formula.unit:
                        raise FormulaError(
                            "DERIVED_TARGET_UNIT", "numeric criterion unit must match exactly"
                        )
                    if scale.type is ScaleType.RATIO and quantity.value < 0:
                        raise FormulaError(
                            "DERIVED_TARGET_VALUE", "ratio measurement cannot be negative"
                        )
                    if (
                        sum(
                            m.alternative_id == alt and m.criterion_id == criterion
                            for m in project.performances
                        )
                        > 1
                    ):
                        raise FormulaError(
                            "DERIVED_DUPLICATE_MEASUREMENT",
                            "resolve duplicate project measurements",
                        )
                    if project.smaa and any(
                        c.alternative_id == alt and c.criterion_id == criterion
                        for c in project.smaa.cells
                    ):
                        raise FormulaError(
                            "DERIVED_UNCERTAINTY_UNSUPPORTED",
                            "target has uncertainty; factor propagation is not supported",
                        )
                    before = raw.get((alt, criterion))
                calculations.append(
                    Calculation(
                        id=formula.id,
                        expression=formula.expression,
                        value=quantity.value,
                        unit=formula.unit,
                        dimension=quantity.dimension,
                        dependencies=sorted(dependencies[formula.id]),
                        source_ids=sorted(upstream[formula.id]),
                        alternative_id=alt,
                        criterion_id=criterion,
                        before=before,
                    )
                )
            except FormulaError as exc:
                error(exc.code, str(exc), path)
                if exc.dimensions:
                    explained.setdefault(path, exc.dimensions)
                if exc.formula_id is not None:
                    failed_in.setdefault(path, exc.formula_id)
    return _Run(calculations=calculations, issues=issues, dimensions=explained, failed_in=failed_in)


def compile_copy(project: Project, model: DerivedModel, review_digest: str) -> Project:
    report = preview(project, model)
    if report.review_digest != review_digest:
        raise StaleRevisionError("Calculation preview changed; review it again before compiling.")
    validation = ValidationReport(issues=report.issues)
    if not validation.ok:
        raise ValidationFailed(validation)
    result = project.model_copy(deep=True)
    for calculation in report.calculations:
        if calculation.alternative_id is not None and calculation.criterion_id is not None:
            result = ps.set_performance(
                result, calculation.alternative_id, calculation.criterion_id, calculation.value
            )
    return result


def compilation_bundle(
    project: Project, model: DerivedModel, review_digest: str
) -> DerivedCompilation:
    """Reuse the authoritative digest/validation gate; no source or library writes."""
    compiled = compile_copy(project, model, review_digest)
    bundle = DerivedCompilation(
        source_project=project.model_copy(deep=True),
        preview=preview(project, model),
        project=compiled,
        compiled_fingerprint=compiled.fingerprint(),
        digest="",
    )
    bundle.digest = _digest(bundle.model_dump(mode="json", exclude={"digest"}))
    return bundle


def verify_bundle(document: DerivedCompilation) -> DerivedCompilation:
    """Check the digest and reconstruct the entire compilation in Python."""
    if document.digest != _digest(document.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("DERIVED_BUNDLE_CHANGED: calculation bundle digest does not match")
    expected = compilation_bundle(
        document.source_project, document.preview.model, document.preview.review_digest
    )
    if expected != document:
        raise ModelEditError("DERIVED_BUNDLE_MISMATCH: calculation bundle does not reproduce")
    return document


def preview_document(
    project: Project, document: DerivedModel | DerivedCompilation
) -> DerivedPreview:
    if isinstance(document, DerivedCompilation):
        # Inspect against the current project as usual, so an old bundle never silently rebinds.
        return preview(project, verify_bundle(document).preview.model)
    return preview(project, document)
