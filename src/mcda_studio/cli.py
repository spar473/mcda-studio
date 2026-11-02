"""Command-line interface: proves every workflow works without touching source code.

mcda new "Supplier Selection" --template supplier-selection -o supplier.json
mcda validate supplier.json
mcda evaluate supplier.json -o results.json
mcda sensitivity supplier.json --criterion delivery
mcda classes set supplier.json --class "Qualified=0.70" --class "Conditional=0.60" --class "Other"
mcda evaluate supplier.json --method mavt_sorting
mcda uncertainty cell supplier.json apex unit_price --uniform 38 46
mcda evaluate supplier.json --method smaa2 --samples 20000 --seed 7
mcda promethee criterion supplier.json unit_price --minimise --weight 3 --linear 2 10
mcda evaluate supplier.json --method promethee2
mcda ahp judge supplier.json --top cost performance 3
mcda evaluate supplier.json --method ahp --synthesis ideal
mcda compare-methods supplier.json
mcda requirement bound supplier.json price_cap unit_price --name "Within budget" --max 45 --unit NZD
mcda feasibility supplier.json
"""

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from mcda_studio.cli_models import model_app, starter_app
from mcda_studio.cli_proxy import proxy_app
from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
    ValueFunctionSpec,
)
from mcda_studio.domain.decision import DecisionDetails, DecisionDraft, DecisionRecord
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import McdaError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.external_proposals import ExternalProposals
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.outranking import (
    AnyPreferenceFunction,
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import AnyRequirement, BoundRequirement, LabelsRequirement
from mcda_studio.domain.results import (
    AcceptabilityEstimate,
    AhpResult,
    MavtSortingResult,
    PrometheeResult,
    SmaaResult,
    SortingSensitivityResult,
    ValueModelResult,
)
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.domain.sorting import SortingAudit, SortingModel
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellRef,
    CellUncertainty,
    DiscreteDistribution,
    Distribution,
    GroupUncertainty,
    SharedDraw,
    SmaaModel,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.methods.ahp.validation import criteria_groups
from mcda_studio.runtime import build_identity, package_version
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import comparison_service as comparisons
from mcda_studio.services import decision_service as decisions
from mcda_studio.services import derived_service as derived
from mcda_studio.services import evidence_service as evidence
from mcda_studio.services import factor_analysis_service as factor_analysis
from mcda_studio.services import feasibility_service as feasibility
from mcda_studio.services import project_service as ps
from mcda_studio.services import questions_service as questions
from mcda_studio.services import templates
from mcda_studio.storage import library_backup as backups
from mcda_studio.storage.json_repository import JsonProjectRepository, save_model, to_json_text
from mcda_studio.storage.library_lock import managed_write

app = typer.Typer(
    help="MCDA Studio - generic multi-criteria decision analysis.", no_args_is_help=True
)
alt_app = typer.Typer(help="Add or remove alternatives.", no_args_is_help=True)
crit_app = typer.Typer(
    help="Edit the criteria tree, scales and value functions.", no_args_is_help=True
)
classes_app = typer.Typer(
    help="Ordered classes for value-based sorting (method mavt_sorting).", no_args_is_help=True
)
library_app = typer.Typer(
    help="Back up, verify and restore a whole project library. Exit 0 = done, "
    "3 = done with warnings, 1 = failed.",
    no_args_is_help=True,
)
app.add_typer(alt_app, name="alternative")
app.add_typer(model_app, name="model-comparisons")
app.add_typer(starter_app, name="starter-templates")
app.add_typer(proxy_app, name="proxy")
app.add_typer(crit_app, name="criterion")
uncertainty_app = typer.Typer(
    help="Stated uncertainty for SMAA-2 (method smaa2): measurement distributions, weight "
    "uncertainty per sibling group and shared draws.",
    no_args_is_help=True,
)
promethee_app = typer.Typer(
    help="PROMETHEE II's own inputs (method promethee2): per leaf, a direction, a weight, a "
    "preference function and, on a labelled scale, a code for each label.",
    no_args_is_help=True,
)
app.add_typer(classes_app, name="classes")
app.add_typer(uncertainty_app, name="uncertainty")
app.add_typer(promethee_app, name="promethee")
ahp_app = typer.Typer(
    help="AHP's pairwise judgements (method ahp): criteria within each sibling group, and the "
    "alternatives on each leaf, on Saaty's 1-9 scale.",
    no_args_is_help=True,
)
app.add_typer(ahp_app, name="ahp")
requirement_app = typer.Typer(
    help="Mandatory requirements on individual measurements, for the feasibility check. No method "
    "reads them and no score offsets a failure.",
    no_args_is_help=True,
)
app.add_typer(requirement_app, name="requirement")
derived_app = typer.Typer(help="Review deterministic formula calculations.", no_args_is_help=True)
app.add_typer(derived_app, name="derived")
evidence_app = typer.Typer(
    help="Review a local evidence dossier and compile a separate project copy.",
    no_args_is_help=True,
)
app.add_typer(evidence_app, name="evidence")
decision_app = typer.Typer(
    help="Create immutable-by-convention local decision snapshots.", no_args_is_help=True
)
app.add_typer(decision_app, name="decision")
app.add_typer(library_app, name="library")

console = Console()
err_console = Console(stderr=True)
repo = JsonProjectRepository()


def _show_version(value: bool) -> None:
    if value:
        console.print(f"mcda-studio {package_version()}")
        console.print(json.dumps(build_identity(), sort_keys=True))
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_show_version, is_eager=True, help="Show build identity."
        ),
    ] = False,
) -> None:
    """Local, transparent decision analysis."""


FileArg = Annotated[Path, typer.Argument(help="Project JSON file.")]
OutOpt = Annotated[Path | None, typer.Option("--output", "-o", help="Write here instead.")]
MethodOpt = Annotated[
    str | None,
    typer.Option(help="View another method once; the saved default is unchanged."),
]


def _configuration(
    project: Project, method: str | None, **ids: str | None
) -> AnalysisConfiguration:
    """The saved configuration with one-off choices. A viewed method other than the saved one runs
    with its own default parameters: one method's parameters are never applied to another."""
    update: dict[str, Any] = {k: v for k, v in ids.items() if v}
    if method and method != project.analysis.method:
        update |= {"method": method, "parameters": {}}
    return project.analysis.model_copy(update=update)


def _fail(message: str) -> NoReturn:
    err_console.print(f"[red]error:[/red] {escape(message)}")
    raise typer.Exit(1)


def _guard[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except ValidationFailed as exc:
        _fail(str(exc))
    except McdaError as exc:
        _fail(str(exc))


def _edit(path: Path, output: Path | None, change: Callable[[Project], Project]) -> None:
    target = output or path
    try:
        with managed_write(target):
            project = _guard(lambda: repo.load(path))
            new = _guard(lambda: change(project))
            _guard(lambda: repo.save(new, target))
    except McdaError as exc:
        _fail(str(exc))
    console.print(f"saved [bold]{escape(str(target))}[/bold]")


def _save_project(project: Project, target: Path) -> Path:
    with managed_write(target):
        return repo.save(project, target)


def _save_result(result: Any, target: Path) -> None:
    with managed_write(target):
        save_model(result, target)


def _save_text(text: str, target: Path) -> None:
    with managed_write(target):
        target.write_text(text, encoding="utf-8")


def _load_dossier(path: Path) -> EvidenceDossier:
    try:
        return EvidenceDossier.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as exc:
        _fail(f"Cannot load evidence dossier: {exc}")


def _new_file(target: Path, contents: str) -> None:
    """Publish a complete file without replacing an existing path."""
    with managed_write(target):
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _load_derived(path: Path) -> DerivedModel:
    try:
        return DerivedModel.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as exc:
        _fail(f"Cannot load calculation model: {exc}")


@derived_app.command("uncertainty-run")
def derived_uncertainty_run(
    file: FileArg,
    model: Annotated[Path, typer.Argument()],
    uncertainty: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Option("--output", "-o")],
    run: Annotated[factor_analysis.Run, typer.Option()] = "smaa2_factors",
    evaluation: Annotated[Literal["sampled", "exact_enumeration"], typer.Option()] = "sampled",
    draws: Annotated[int, typer.Option()] = 1000,
    seed: Annotated[int, typer.Option()] = 7,
    profile: Annotated[str | None, typer.Option()] = None,
    scenario: Annotated[str | None, typer.Option()] = None,
    decision: Annotated[
        Path | None, typer.Option(help="Optional decision-details JSON snapshot.")
    ] = None,
) -> None:
    """Evaluate reviewed factor uncertainty into a new sealed record; inputs are never changed."""
    project = _guard(lambda: repo.load(file))
    try:
        spec = FactorUncertaintyModel.model_validate_json(uncertainty.read_text(encoding="utf-8"))
        details = (
            DecisionDetails.model_validate_json(decision.read_text(encoding="utf-8"))
            if decision
            else None
        )
        parameters = factor_analysis.FactorRunParameters(
            run=run,
            evaluation=evaluation,
            draws=draws,
            seed=seed,
            configuration=AnalysisConfiguration(weight_profile_id=profile, scenario_id=scenario),
        )
    except (OSError, UnicodeError, ValidationError) as exc:
        _fail(str(exc))
    record = _guard(
        lambda: factor_analysis.run(project, _load_derived(model), spec, parameters, details)
    )
    try:
        _new_file(output, record.model_dump_json(indent=2) + "\n")
    except (OSError, McdaError) as exc:
        _fail(str(exc))
    console.print(f"created [bold]{escape(str(output))}[/bold]")


@derived_app.command("verify-uncertainty")
def verify_derived_uncertainty(
    file: FileArg, replay: Annotated[bool, typer.Option()] = False
) -> None:
    """Verify a retained factor run; replay is explicit and environment-bound."""
    try:
        body = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    _guard(lambda: factor_analysis.verify(body, replay))
    console.print("Factor run verified.")


@derived_app.command("preview")
def derived_preview(file: FileArg, model: Annotated[Path, typer.Argument()]) -> None:
    """Print reproducible calculations, provenance, dependencies and the review digest."""
    project = _guard(lambda: repo.load(file))
    report = _guard(lambda: derived.preview(project, _load_derived(model)))
    console.print_json(data=report.model_dump(mode="json"))


@derived_app.command("compile")
def derived_compile(
    file: FileArg,
    model: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Option("--output", "-o", help="New static project copy.")],
    review_digest: Annotated[str, typer.Option(help="Digest from the reviewed preview.")],
) -> None:
    """Compile accepted calculations to a new file; retain the model and preview for provenance."""
    project = _guard(lambda: repo.load(file))
    result = _guard(lambda: derived.compile_copy(project, _load_derived(model), review_digest))
    try:
        _new_file(output, to_json_text(result))
    except (OSError, McdaError) as exc:
        _fail(f"Cannot write new project: {exc}")
    console.print(f"created [bold]{escape(str(output))}[/bold]")


@evidence_app.command("preview")
def evidence_preview(
    file: FileArg, dossier: Annotated[Path, typer.Argument(help="Evidence dossier JSON.")]
) -> None:
    """Print the exact changes and review digest; this does not edit the project."""
    project = _guard(lambda: repo.load(file))
    report = _guard(lambda: evidence.preview(project, _load_dossier(dossier)))
    console.print_json(data=report.model_dump(mode="json"))


@evidence_app.command("compile")
def evidence_compile(
    file: FileArg,
    dossier: Annotated[Path, typer.Argument(help="Evidence dossier JSON.")],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="New project file; never overwritten.")
    ],
    review_digest: Annotated[str, typer.Option(help="Digest from the reviewed preview.")],
) -> None:
    """Write a new project from a reviewed preview; existing files are never overwritten."""
    project = _guard(lambda: repo.load(file))
    result = _guard(lambda: evidence.compile_copy(project, _load_dossier(dossier), review_digest))
    try:
        _new_file(output, to_json_text(result))
    except (OSError, McdaError) as exc:
        _fail(f"Cannot write new project: {exc}")
    console.print(f"created [bold]{escape(str(output))}[/bold]")


@decision_app.command("record")
def decision_record(
    file: FileArg,
    draft: Annotated[Path, typer.Argument(help="Decision details JSON.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="New record file.")],
    previous: Annotated[Path | None, typer.Option(help="Previous decision record.")] = None,
    evidence_file: Annotated[Path | None, typer.Option(help="Evidence dossier JSON.")] = None,
    evidence_project: Annotated[Path | None, typer.Option(help="Dossier's source project.")] = None,
) -> None:
    """Capture the project, complete analyses, rationale and optional evidence in a new record."""
    try:
        details = DecisionDraft.model_validate_json(draft.read_text(encoding="utf-8"))
        predecessor = (
            DecisionRecord.model_validate_json(previous.read_text(encoding="utf-8"))
            if previous
            else None
        )
        project = repo.load(file)
        source = repo.load(evidence_project) if evidence_project else None
        dossier = _load_dossier(evidence_file) if evidence_file else None
        record = decisions.create(project, details, predecessor, source, dossier)
        _new_file(output, to_json_text(record))
    except (OSError, UnicodeError, ValidationError, McdaError) as exc:
        _fail(f"Cannot create decision record: {exc}")
    console.print(f"created [bold]{escape(str(output))}[/bold] (digest {record.digest})")


# ---- project-level commands ---------------------------------------------------------------
@app.command("open-questions")
def open_questions(
    file: FileArg,
    evidence_file: Annotated[
        Path | None, typer.Option(help="Optional evidence dossier JSON.")
    ] = None,
) -> None:
    """List research questions for the project and an optional local evidence dossier."""
    project = _guard(lambda: repo.load(file))
    dossier = _load_dossier(evidence_file) if evidence_file else None
    report = _guard(lambda: questions.open_questions(project, dossier=dossier))
    console.print_json(data=report.model_dump(mode="json"))


@app.command()
def new(
    title: Annotated[str, typer.Argument(help="Project title.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Where to write the project.")],
    method: Annotated[str, typer.Option(help="MCDA method.")] = "mavt",
    template: Annotated[str, typer.Option(help="blank or supplier-selection.")] = "blank",
) -> None:
    """Create a blank project (or one from a template) and save it."""

    def build() -> Project:
        p = templates.from_template(template, title)
        return p.model_copy(update={"analysis": p.analysis.model_copy(update={"method": method})})

    project = _guard(build)
    _guard(lambda: _save_project(project, output))
    console.print(f"created [bold]{output}[/bold] ({template} template, method {method})")


@app.command("templates")
def list_templates() -> None:
    """List available project templates."""
    for name in sorted(templates.TEMPLATES):
        console.print(name)


@app.command()
def validate(file: FileArg) -> None:
    """Check model completeness. Exit code 1 if there are errors."""
    project = _guard(lambda: repo.load(file))
    report = svc.validate(project)
    if project.analysis.method != "mavt":  # the saved method's own rules, e.g. sorting classes
        seen = {(i.code, i.path, i.message) for i in report.issues}
        own = _guard(lambda: svc.validate_effective(project)).validation.issues
        report = report.model_copy(
            update={
                "issues": [
                    *report.issues,
                    *(i for i in own if (i.code, i.path, i.message) not in seen),
                ]
            }
        )
    if not report.issues:
        console.print("[green]valid[/green]: no issues")
        return
    table = Table("severity", "code", "where", "message")
    for i in report.issues:
        colour = {"error": "red", "warning": "yellow"}.get(i.severity.value, "blue")
        table.add_row(
            f"[{colour}]{i.severity.value}[/{colour}]", i.code, escape(i.path), escape(i.message)
        )
    console.print(table)
    if not report.ok:
        console.print(
            f"[red]{len(report.errors)} error(s)[/red], {len(report.warnings)} warning(s)"
        )
        raise typer.Exit(1)
    console.print(f"[green]valid[/green] with {len(report.warnings)} warning(s)")


@app.command()
def evaluate(
    file: FileArg,
    output: OutOpt = None,
    profile: Annotated[str | None, typer.Option(help="Weight profile id.")] = None,
    scenario: Annotated[str | None, typer.Option(help="Scenario id.")] = None,
    method: MethodOpt = None,
    samples: Annotated[int | None, typer.Option(help="SMAA-2 draws (1000 to 100000).")] = None,
    seed: Annotated[int | None, typer.Option(help="SMAA-2 seed.")] = None,
    uncertainty: Annotated[
        str | None, typer.Option(help="SMAA-2 run: performance, preference or combined.")
    ] = None,
    synthesis: Annotated[
        str | None, typer.Option(help="AHP synthesis: distributive or ideal.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print full result JSON.")] = False,
) -> None:
    """Calculate rankings and save the full inspectable result."""
    project = _guard(lambda: repo.load(file))
    cfg = _configuration(project, method, weight_profile_id=profile, scenario_id=scenario)
    run = {"samples": samples, "seed": seed, "uncertainty": uncertainty, "synthesis": synthesis}
    if any(v is not None for v in run.values()):
        given = {k: v for k, v in run.items() if v is not None}
        cfg = cfg.model_copy(update={"parameters": {**cfg.parameters, **given}})
    result = _guard(lambda: svc.evaluate_project(project, cfg))
    if output:
        _guard(lambda: _save_result(result, output))
    if as_json:
        typer.echo(to_json_text(result), nl=False)
        return
    if isinstance(result, SmaaResult | PrometheeResult | AhpResult):
        if isinstance(result, SmaaResult):
            _print_acceptability(result)
        elif isinstance(result, PrometheeResult):
            _print_flows(result)
        else:
            _print_priorities(result)
        _print_feasibility_beside(project)
        if output:
            console.print(f"result written to [bold]{output}[/bold]")
        return
    if isinstance(result, MavtSortingResult):
        names = {c.class_id: c.name for c in result.classes}
        assigned = {a.alternative_id: a for a in result.assignments}
        table = Table("rank", "alternative", "value", "class", "to nearest boundary")
        for r in result.ranking:
            a = assigned[r.alternative_id]
            distance = a.distance_to_nearest_boundary
            table.add_row(
                str(r.rank),
                escape(r.name),
                f"{r.value:.4f}",
                escape(names[a.class_id]),
                "-" if distance is None else f"{distance:.4f}" + (" (on)" if a.on_boundary else ""),
            )
    else:
        table = Table("rank", "alternative", "value")
        for r in result.ranking:
            table.add_row(str(r.rank), escape(r.name), f"{r.value:.4f}")
    console.print(table)
    if isinstance(result, MavtSortingResult) and result.audit_sample:
        sample = result.audit_sample
        console.print(
            f"audit sample below {escape(names[sample.below_class_id])} "
            f"({len(sample.alternative_ids)} of {sample.pool_size}, seed {sample.seed}): "
            f"{', '.join(sample.alternative_ids) or 'none'}"
        )
    if isinstance(result, ValueModelResult):
        wt = Table("criterion", "global weight")
        for leaf, w in result.global_weights.items():
            wt.add_row(leaf, f"{w:.4f}")
        console.print(wt)
    for d in result.diagnostics:
        console.print(f"[dim]{d.severity.value}: {escape(d.message)}[/dim]")
    _print_feasibility_beside(project)
    if output:
        console.print(f"result written to [bold]{output}[/bold]")


def _print_feasibility_beside(project: Project) -> None:
    """Each alternative's feasibility beside a ranking, when the project states requirements.
    The ranking above is unchanged: no score offsets a failure, and nothing is hidden."""
    if not project.requirements:
        return
    try:
        result = feasibility.check_feasibility(project)
    except McdaError as exc:
        console.print(f"feasibility not checked: {escape(str(exc).splitlines()[0])}")
        return
    parts = []
    for a in result.alternatives:
        detail = f" ({', '.join(a.failed or a.unknown)})" if a.status != "pass" else ""
        parts.append(f"{escape(a.name)} {a.status}{detail}")
    console.print("feasibility: " + "; ".join(parts))


def _estimate(e: AcceptabilityEstimate) -> str:
    if e.lower is None or e.upper is None:
        return f"{e.frequency:.4f}"
    return f"{e.frequency:.4f} [{e.lower:.4f}, {e.upper:.4f}]"


def _print_acceptability(result: SmaaResult) -> None:
    kind = (
        f"{result.samples} draws, seed {result.seed}, {result.confidence:.0%} Clopper-Pearson"
        if result.evaluation == "sampled"
        else f"exact over {result.outcomes} outcomes"
    )
    console.print(f"[bold]{result.label}[/bold] ({result.run} run; {kind})")
    table = Table("alternative", "rank 1", "sole first", "tied first", "other ranks")
    for a in result.acceptability:
        rest = ", ".join(
            f"{r + 2}: {e.frequency:.4f}" for r, e in enumerate(a.ranks[1:]) if e.frequency
        )
        table.add_row(
            escape(a.name),
            _estimate(a.ranks[0]),
            _estimate(a.sole_first),
            _estimate(a.tied_first),
            rest or "-",
        )
    console.print(table)
    if result.classes:
        classes = Table("alternative", *(escape(c.name) for c in result.classes))
        for a in result.acceptability:
            classes.add_row(
                escape(a.name), *(_estimate(a.classes[c.class_id]) for c in result.classes)
            )
        console.print(classes)
    if result.inputs_to_check:
        console.print(f"inputs to check ({result.inputs_to_check_label}):")
        for x in result.inputs_to_check:
            console.print(
                f"  {escape(x.input)}: leader rank 1 {x.leader_rank1_upper_half:.4f} (upper half) "
                f"vs {x.leader_rank1_lower_half:.4f} (lower half)"
            )
    for d in result.diagnostics:
        console.print(f"[dim]{d.severity.value}: {escape(d.message)}[/dim]")


def _print_flows(result: PrometheeResult) -> None:
    """Flows under their label, never as values; then PROMETHEE I and the explanation."""
    names = {f.alternative_id: f.name for f in result.flows}
    console.print(f"[bold]{result.label}[/bold]")
    table = Table("rank", "alternative", "positive flow", "negative flow", "net flow")
    for f in result.flows:
        table.add_row(
            str(f.rank),
            escape(f.name),
            f"{f.positive_flow:.4f}",
            f"{f.negative_flow:.4f}",
            f"{f.net_flow:+.4f}",
        )
    console.print(table)
    incomparable = [p for p in result.partial_order if p.relation == "incomparable"]
    console.print(
        "PROMETHEE I incomparable pairs: "
        + (
            ", ".join(
                f"{escape(names[p.alternative_a])} and {escape(names[p.alternative_b])}"
                for p in incomparable
            )
            or "none"
        )
    )
    explanation = result.explanation
    if not explanation.available:
        codes = ", ".join(explanation.unavailable_codes)
        console.print(
            f"explanation against MAVT unavailable: {explanation.unavailable_reason}"
            + (f" ({codes})" if codes else "")
        )
    else:
        ranks = Table("alternative", "MAVT rank", "PROMETHEE II rank")
        for r in explanation.ranks:
            ranks.add_row(escape(r.name), str(r.mavt_rank), str(r.promethee_rank))
        console.print(ranks)
        if not explanation.pairs:
            console.print("MAVT and PROMETHEE II order every pair the same way")
        for pair in explanation.pairs:
            a, b = escape(names[pair.alternative_a]), escape(names[pair.alternative_b])
            console.print(
                f"{a} (MAVT rank {pair.mavt_rank_a}, PROMETHEE II rank {pair.promethee_rank_a}) "
                f"and {b} (MAVT rank {pair.mavt_rank_b}, PROMETHEE II rank "
                f"{pair.promethee_rank_b}): value gap {pair.value_gap:+.4f}, flow gap "
                f"{pair.flow_gap:+.4f} (head-to-head {pair.head_to_head:+.4f}, via others "
                f"{pair.via_others:+.4f})"
            )
            for reason in pair.reasons:
                console.print(f"  - {escape(reason)}")
    for d in result.diagnostics:
        console.print(f"[dim]{d.severity.value}: {escape(d.message)}[/dim]")


def _fraction(value: float) -> str:
    """A matrix entry as a judgement reads: 3, or 1/3 for its reciprocal."""
    return f"{value:.4g}" if value >= 1 else f"1/{1 / value:.4g}"


def _consistency_table(
    rows: list[tuple[str, int, float, bool, str]],
) -> Table:
    table = Table("matrix", "items", "CR", "", "most inconsistent triad")
    for name, n, cr, flagged, triad in rows:
        table.add_row(name, str(n), f"{cr:.4f}", "above 0.10" if flagged else "", triad)
    return table


def _triad_text(triad: Any) -> str:
    if triad is None:
        return "-"
    a, b, c = triad.items
    x, y, z = triad.judgements
    return (
        f"{a}/{b} {_fraction(x)}, {b}/{c} {_fraction(y)}, {a}/{c} {_fraction(z)} "
        f"(consistent: {_fraction(triad.consistent_value)})"
    )


def _print_priorities(result: AhpResult) -> None:
    """Priorities under their label, never as values; then every matrix's consistency."""
    console.print(f"[bold]{result.label}[/bold]")
    console.print(f"{result.synthesis} synthesis; random index {result.random_index_table}")
    ideal = result.synthesis == "ideal"
    table = Table("rank", "alternative", "AHP priority", *(["ideal score"] if ideal else []))
    for a in result.alternatives:
        extra = [f"{a.ideal_score:.4f}"] if ideal and a.ideal_score is not None else []
        table.add_row(str(a.rank), escape(a.name), f"{a.priority:.4f}", *extra)
    console.print(table)
    rows = []
    for m in result.matrices:
        group = "top level" if m.group_id is None else m.group_id
        name = f"{'criteria' if m.kind == 'criteria' else 'alternatives'} under {group}"
        rows.append(
            (
                name,
                len(m.items),
                m.consistency_ratio,
                m.inconsistent,
                _triad_text(m.most_inconsistent_triad),
            )
        )
    console.print(_consistency_table(rows))
    for d in result.diagnostics:
        console.print(f"[dim]{d.severity.value}: {escape(d.message)}[/dim]")


@app.command("compare-methods")
def compare_methods(
    file: FileArg,
    method: Annotated[
        list[str] | None, typer.Option(help="Method to include (repeat); all by default.")
    ] = None,
    profile: Annotated[str | None, typer.Option(help="Weight profile id.")] = None,
    scenario: Annotated[str | None, typer.Option(help="Scenario id.")] = None,
    output: OutOpt = None,
) -> None:
    """Every method's own reading of the model, side by side; never a combined score."""
    project = _guard(lambda: repo.load(file))
    cfg = project.analysis.model_copy(
        update={"weight_profile_id": profile, "scenario_id": scenario}
    )
    result = _guard(lambda: comparisons.compare_methods(project, cfg, method))
    table = Table("alternative")
    for column in result.columns:
        table.add_column(
            f"{escape(column.method_label)}\n{column.quantity_name or ''}"
            if column.status == "ok"
            else escape(column.method_label)
        )
    cells = {c.method: {cell.alternative_id: cell for cell in c.cells} for c in result.columns}
    for alt in result.alternative_order:
        row = [escape(result.alternative_names[alt])]
        for column in result.columns:
            if column.error is not None:
                row.append(column.error.code)
                continue
            cell = cells[column.method][alt]
            text = f"{cell.rank} ({cell.quantity:.4f})"
            if cell.class_id:
                text += f" {cell.class_id}"
            row.append(text)
        table.add_row(*row)
    console.print(table)
    for column in result.columns:
        if column.error is not None:
            codes = ", ".join(column.error.issue_codes)
            console.print(
                f"{escape(column.method_label)} did not run: {column.error.code}"
                + (f" ({codes})" if codes else "")
            )
    agreement = result.agreement
    names = result.alternative_names
    if agreement.leaders_agree is None:
        console.print("fewer than two methods ran: nothing to compare")
    elif agreement.leaders_agree:
        leader = names[agreement.leader_groups[0].leaders[0]]
        console.print(f"every method that ran puts {escape(leader)} first")
    else:
        for group in agreement.leader_groups:
            first = ", ".join(escape(names[i]) for i in group.leaders)
            console.print(f"first: {first} - {', '.join(group.methods)}")
    for c in agreement.classes:
        if not c.agree:
            console.print(
                f"{escape(names[c.alternative_id])}: sorting {c.sorting_class_id}, SMAA-2 most "
                f"often {c.smaa_class_id} ({c.smaa_class_share:.1%})"
            )
    for reason in agreement.reasons:
        console.print(f"{reason.method}:")
        for text in reason.reasons:
            console.print(f"  - {escape(text)}")
    console.print(f"[dim]{agreement.context}[/dim]")
    _print_feasibility_beside(project)
    if output:
        _guard(lambda: _save_result(result, output))
        console.print(f"comparison written to [bold]{output}[/bold]")


@app.command()
def sensitivity(
    file: FileArg,
    criterion: Annotated[str | None, typer.Option(help="Criterion node id to vary.")] = None,
    all_nodes: Annotated[bool, typer.Option("--all", help="Analyse every eligible node.")] = False,
    steps: Annotated[int, typer.Option(help="Grid points over [0, 1].")] = 101,
    method: MethodOpt = None,
    output: OutOpt = None,
) -> None:
    """One-way weight sensitivity: crossovers, first winner changes and, when sorting, the first
    class changes."""
    if bool(criterion) == all_nodes:
        _fail("give exactly one of --criterion ID or --all")
    project = _guard(lambda: repo.load(file))
    cfg = _configuration(project, method)
    results = (
        _guard(lambda: svc.sensitivity_all(project, cfg, steps=steps))
        if all_nodes
        else [_guard(lambda: svc.sensitivity(project, str(criterion), cfg, steps=steps))]
    )
    table = Table("criterion", "base weight", "winner up", "winner down", "ranking stable on")
    for r in results:
        up = (
            f"{r.first_winner_change_up.to_winner} @ {r.first_winner_change_up.weight:.4f}"
            if r.first_winner_change_up
            else "-"
        )
        dn = (
            f"{r.first_winner_change_down.to_winner} @ {r.first_winner_change_down.weight:.4f}"
            if r.first_winner_change_down
            else "-"
        )
        lo, hi = r.ranking_stable_range
        table.add_row(r.node_id, f"{r.base_weight:.4f}", up, dn, f"[{lo:.4f}, {hi:.4f}]")
    console.print(table)
    first = results[0] if results else None
    if not all_nodes and isinstance(first, SortingSensitivityResult):
        names = {c.class_id: c.name for c in first.classes}

        def change(c: Any, raising: bool) -> str:
            """Raising the weight past a change leads to the class above; lowering, below."""
            if c is None:
                return "-"
            return f"{escape(names[c.class_after if raising else c.class_before])} @ {c.weight:.4f}"

        classes = Table("alternative", "class at base", "first change up", "first change down")
        for c in first.class_changes:
            classes.add_row(
                c.alternative_id,
                escape(names[c.base_class_id]),
                change(c.first_change_up, True),
                change(c.first_change_down, False),
            )
        console.print(classes)
    if all_nodes:
        analysed = {r.node_id for r in results}
        skipped = [n for n in project.tree().all_ids() if n not in analysed]
        if skipped:
            console.print(
                "not analysed (no siblings to rebalance, or the node already carries the whole "
                f"local weight): {', '.join(skipped)}"
            )
    if output:
        payload: Any = results[0] if not all_nodes else None
        if payload is not None:
            _guard(lambda: _save_result(payload, output))
        else:
            text = json.dumps([r.model_dump(mode="json") for r in results], indent=2) + "\n"
            _guard(lambda: _save_text(text, output))
        console.print(f"written to [bold]{output}[/bold]")


@app.command()
def compare(
    file: FileArg,
    scenario: Annotated[list[str] | None, typer.Option(help="Scenario id (repeatable).")] = None,
    method: MethodOpt = None,
) -> None:
    """Compare the baseline with value-function / weight scenarios."""
    project = _guard(lambda: repo.load(file))
    cmp = _guard(lambda: svc.compare_scenarios(project, scenario, _configuration(project, method)))
    table = Table("scenario", "ranking", "ranking changed", "winner changed")
    table.add_row("baseline", " > ".join(cmp.baseline.ranking), "-", "-")
    for s in cmp.scenarios:
        table.add_row(
            escape(s.scenario_name),
            " > ".join(s.ranking),
            str(s.ranking_differs_from_baseline),
            str(s.winner_differs_from_baseline),
        )
    console.print(table)


@app.command()
def duplicate(
    file: FileArg,
    output: Annotated[Path, typer.Option("--output", "-o", help="New project file.")],
    title: Annotated[str | None, typer.Option(help="Title for the copy.")] = None,
) -> None:
    """Copy a project (new id) without touching the original."""
    project = _guard(lambda: repo.load(file))
    _guard(lambda: _save_project(ps.duplicate_project(project, title), output))
    console.print(f"duplicated to [bold]{output}[/bold]")


@app.command("method")
def set_method(
    file: FileArg,
    name: Annotated[str, typer.Argument(help="Method name, e.g. mavt or mavt_sorting.")],
    output: OutOpt = None,
) -> None:
    """Set the saved method. Changing it clears the saved method parameters."""
    _edit(file, output, lambda p: ps.set_analysis_method(p, name))


# ---- value-based sorting ------------------------------------------------------------------
def _parse_class(text: str) -> tuple[str, float | None]:
    name, sep, boundary = text.rpartition("=")
    if not sep:
        return text, None
    try:
        return name, float(boundary)
    except ValueError:
        _fail(f"{text!r}: the boundary after '=' must be a number")


@classes_app.command("set")
def classes_set(
    file: FileArg,
    classes: Annotated[
        list[str],
        typer.Option(
            "--class",
            help="NAME=LOWER_BOUNDARY, best class first; the lowest class has no boundary.",
        ),
    ],
    output: OutOpt = None,
) -> None:
    """Replace the ordered classes. Boundaries are never reordered: a wrong order is an error."""
    parsed = [_parse_class(c) for c in classes]

    def change(p: Project) -> Project:
        audit = p.sorting.audit if p.sorting else None
        model = SortingModel(classes=ps.sorting_classes(parsed), audit=audit)
        return ps.set_sorting_model(p, model)

    _edit(file, output, change)


@classes_app.command("audit")
def classes_audit(
    file: FileArg,
    below: Annotated[
        str | None, typer.Option(help="Sample from classes below this class id.")
    ] = None,
    size: Annotated[int, typer.Option(help="How many alternatives to sample.")] = 1,
    seed: Annotated[int, typer.Option(help="Seed for the sample.")] = 0,
    off: Annotated[bool, typer.Option("--off", help="Remove the audit sample.")] = False,
    output: OutOpt = None,
) -> None:
    """Set or remove the audit sample of alternatives sorted below a cut-off class."""
    if off == bool(below):
        _fail("give exactly one of --below CLASS or --off")

    def change(p: Project) -> Project:
        if p.sorting is None:
            raise McdaError("the project has no classes; add them with 'mcda classes set'")
        audit = (
            None if off else SortingAudit(below_class_id=str(below), sample_size=size, seed=seed)
        )
        return ps.set_sorting_model(p, p.sorting.model_copy(update={"audit": audit}))

    _edit(file, output, change)


@classes_app.command("clear")
def classes_clear(file: FileArg, output: OutOpt = None) -> None:
    """Remove the classes; a project without other method sections is saved as version 1 again."""
    _edit(file, output, ps.clear_sorting_model)


# ---- stated uncertainty (SMAA-2) ------------------------------------------------------------
def _outcomes(text: str) -> tuple[list[str], list[float]]:
    """``"a=0.3,b=0.7"`` into outcomes and probabilities."""
    keys: list[str] = []
    probabilities: list[float] = []
    for part in text.split(","):
        key, sep, probability = part.rpartition("=")
        try:
            if not sep:
                raise ValueError
            probabilities.append(float(probability))
        except ValueError:
            _fail(f"{part!r}: write each outcome as OUTCOME=PROBABILITY")
        keys.append(key.strip())
    return keys, probabilities


def _smaa(p: Project) -> SmaaModel:
    return p.smaa.model_copy(deep=True) if p.smaa else SmaaModel()


@uncertainty_app.command("cell")
def uncertainty_cell(
    file: FileArg,
    alternative: Annotated[str, typer.Argument(help="Alternative id.")],
    criterion: Annotated[str, typer.Argument(help="Leaf criterion id.")],
    uniform: Annotated[tuple[float, float] | None, typer.Option(help="LOWER UPPER.")] = None,
    triangular: Annotated[
        tuple[float, float, float] | None, typer.Option(help="LOWER MODE UPPER.")
    ] = None,
    discrete: Annotated[str | None, typer.Option(help="VALUE=P,VALUE=P,...")] = None,
    categorical: Annotated[str | None, typer.Option(help="LABEL=P,LABEL=P,...")] = None,
    remove: Annotated[
        bool, typer.Option("--remove", help="Remove this cell's distribution.")
    ] = False,
    output: OutOpt = None,
) -> None:
    """State, replace or remove one measurement's distribution."""
    if sum(x is not None for x in (uniform, triangular, discrete, categorical)) + remove != 1:
        _fail("give exactly one of --uniform, --triangular, --discrete, --categorical or --remove")
    dist: Distribution | None = None
    if uniform:
        dist = UniformDistribution(lower=uniform[0], upper=uniform[1])
    elif triangular:
        dist = TriangularDistribution(lower=triangular[0], mode=triangular[1], upper=triangular[2])
    elif discrete:
        values, probabilities = _outcomes(discrete)
        try:
            numbers = [float(v) for v in values]
        except ValueError:
            _fail("discrete outcomes must be numbers")
        dist = DiscreteDistribution(values=numbers, probabilities=probabilities)
    elif categorical:
        labels, probabilities = _outcomes(categorical)
        dist = CategoricalDistribution(labels=labels, probabilities=probabilities)

    def change(p: Project) -> Project:
        model = _smaa(p)
        model.cells = [
            c for c in model.cells if (c.alternative_id, c.criterion_id) != (alternative, criterion)
        ]
        if dist is not None:
            model.cells.append(
                CellUncertainty(
                    alternative_id=alternative, criterion_id=criterion, distribution=dist
                )
            )
        return ps.set_smaa_model(p, model)

    _edit(file, output, change)


@uncertainty_app.command("group")
def uncertainty_group(
    file: FileArg,
    parent: Annotated[
        str | None, typer.Option(help="Parent criterion id; omit for the top level.")
    ] = None,
    unknown: Annotated[bool, typer.Option("--unknown", help="Uniform local weights.")] = False,
    interval: Annotated[
        list[str] | None, typer.Option(help="CHILD=LOWER:UPPER raw rating interval (repeat).")
    ] = None,
    fixed: Annotated[bool, typer.Option("--fixed", help="Back to the profile's ratings.")] = False,
    output: OutOpt = None,
) -> None:
    """Set a sibling group's weight uncertainty."""
    if unknown + fixed + bool(interval) != 1:
        _fail("give exactly one of --unknown, --interval or --fixed")
    intervals: dict[str, tuple[float, float]] = {}
    for item in interval or []:
        child, sep, bounds = item.partition("=")
        lo, sep2, hi = bounds.partition(":")
        try:
            if not (sep and sep2):
                raise ValueError
            intervals[child] = (float(lo), float(hi))
        except ValueError:
            _fail(f"{item!r}: write each interval as CHILD=LOWER:UPPER")

    def change(p: Project) -> Project:
        model = _smaa(p)
        model.groups = [g for g in model.groups if g.parent_id != parent]
        if not fixed:
            kind = "unknown" if unknown else "rating_intervals"
            model.groups.append(GroupUncertainty(parent_id=parent, kind=kind, intervals=intervals))
        return ps.set_smaa_model(p, model)

    _edit(file, output, change)


@uncertainty_app.command("share")
def uncertainty_share(
    file: FileArg,
    draw: Annotated[str, typer.Argument(help="Shared draw id.")],
    cell: Annotated[list[str], typer.Option(help="ALTERNATIVE:CRITERION (repeat).")],
    output: OutOpt = None,
) -> None:
    """Make cells from one source use one common draw."""
    refs = []
    for item in cell:
        alternative, sep, criterion = item.partition(":")
        if not sep:
            _fail(f"{item!r}: write each cell as ALTERNATIVE:CRITERION")
        refs.append(CellRef(alternative_id=alternative, criterion_id=criterion))

    def change(p: Project) -> Project:
        model = _smaa(p)
        model.shared_draws = [s for s in model.shared_draws if s.id != draw]
        model.shared_draws.append(SharedDraw(id=draw, cells=refs))
        return ps.set_smaa_model(p, model)

    _edit(file, output, change)


@uncertainty_app.command("clear")
def uncertainty_clear(file: FileArg, output: OutOpt = None) -> None:
    """Remove all stated uncertainty; the project returns to the lowest version it needs."""
    _edit(file, output, ps.clear_smaa_model)


# ---- PROMETHEE II inputs ----------------------------------------------------------------------
def _promethee(p: Project) -> PrometheeModel:
    return p.promethee.model_copy(deep=True) if p.promethee else PrometheeModel()


@promethee_app.command("criterion")
def promethee_criterion(
    file: FileArg,
    criterion: Annotated[str, typer.Argument(help="Leaf criterion id.")],
    weight: Annotated[float, typer.Option(help="Non-negative weight; normalised by the sum.")],
    maximise: Annotated[bool, typer.Option("--maximise", help="Higher is better.")] = False,
    minimise: Annotated[bool, typer.Option("--minimise", help="Lower is better.")] = False,
    usual: Annotated[
        bool, typer.Option("--usual", help="Any difference is full preference (default).")
    ] = False,
    u_shape: Annotated[
        float | None, typer.Option("--u-shape", help="Q: full preference beyond q.")
    ] = None,
    v_shape: Annotated[
        float | None, typer.Option("--v-shape", help="P: linear up to full preference at p.")
    ] = None,
    linear: Annotated[
        tuple[float, float] | None,
        typer.Option(help="Q P: none up to q, linear to full preference at p."),
    ] = None,
    code: Annotated[
        list[str] | None, typer.Option(help="LABEL=NUMBER for a labelled leaf (repeat).")
    ] = None,
    output: OutOpt = None,
) -> None:
    """State or replace one leaf's direction, weight, preference function and codes."""
    if maximise == minimise:
        _fail("give exactly one of --maximise or --minimise")
    if usual + (u_shape is not None) + (v_shape is not None) + (linear is not None) > 1:
        _fail("give at most one of --usual, --u-shape, --v-shape or --linear")
    function: AnyPreferenceFunction = UsualFunction()
    if u_shape is not None:
        function = UShapeFunction(q=u_shape)
    elif v_shape is not None:
        function = VShapeFunction(p=v_shape)
    elif linear is not None:
        function = LinearPreferenceFunction(q=linear[0], p=linear[1])
    coding: dict[str, float] | None = None
    for item in code or []:
        label, sep, number = item.rpartition("=")
        try:
            if not sep:
                raise ValueError
            coding = {**(coding or {}), label: float(number)}
        except ValueError:
            _fail(f"{item!r}: write each code as LABEL=NUMBER")
    entry = PrometheeCriterion(
        criterion_id=criterion,
        direction="maximise" if maximise else "minimise",
        weight=weight,
        function=function,
        coding=coding,
    )

    def change(p: Project) -> Project:
        model = _promethee(p)
        at = next((k for k, c in enumerate(model.criteria) if c.criterion_id == criterion), None)
        if at is None:
            model.criteria.append(entry)
        else:
            model.criteria[at] = entry
        return ps.set_promethee_model(p, model)

    _edit(file, output, change)


@promethee_app.command("remove")
def promethee_remove(
    file: FileArg,
    criterion: Annotated[str, typer.Argument(help="Leaf criterion id.")],
    output: OutOpt = None,
) -> None:
    """Remove one leaf's PROMETHEE entry."""

    def change(p: Project) -> Project:
        model = _promethee(p)
        model.criteria = [c for c in model.criteria if c.criterion_id != criterion]
        return ps.set_promethee_model(p, model)

    _edit(file, output, change)


@promethee_app.command("clear")
def promethee_clear(file: FileArg, output: OutOpt = None) -> None:
    """Remove every PROMETHEE input; the project returns to the lowest version it needs."""
    _edit(file, output, ps.clear_promethee_model)


# ---- AHP judgements ------------------------------------------------------------------------
def _ahp(p: Project) -> AhpModel:
    return p.ahp.model_copy(deep=True) if p.ahp else AhpModel()


TopOpt = Annotated[bool, typer.Option("--top", help="Judge the top-level criteria.")]
GroupOpt = Annotated[
    str | None, typer.Option("--group", help="Judge the children of this criterion.")
]
LeafOpt = Annotated[
    str | None, typer.Option("--leaf", help="Judge the alternatives on this leaf criterion.")
]


def _matrix_judgements(
    model: AhpModel, top: bool, group: str | None, leaf: str | None
) -> list[PairwiseJudgement]:
    """The judgement list of the chosen matrix, created empty if the section lacks it."""
    if top + (group is not None) + (leaf is not None) != 1:
        _fail("give exactly one of --top, --group PARENT or --leaf LEAF")
    if leaf is not None:
        for entry in model.alternatives:
            if entry.criterion_id == leaf:
                return entry.judgements
        model.alternatives.append(AlternativeJudgements(criterion_id=leaf))
        return model.alternatives[-1].judgements
    for g in model.criteria:
        if g.parent_id == group:
            return g.judgements
    model.criteria.append(CriteriaJudgements(parent_id=group))
    return model.criteria[-1].judgements


@ahp_app.command("judge")
def ahp_judge(
    file: FileArg,
    row: Annotated[str, typer.Argument(help="The favoured item (either, when equal).")],
    column: Annotated[str, typer.Argument(help="The other item.")],
    value: Annotated[float, typer.Argument(help="How many times as important: 1 to 9.")],
    top: TopOpt = False,
    group: GroupOpt = None,
    leaf: LeafOpt = None,
    output: OutOpt = None,
) -> None:
    """State or replace one pairwise judgement; its reciprocal is derived."""
    if value < 1:
        _fail(f"{value:g} is below 1: swap ROW and COLUMN and give {1 / value:g} instead")

    def change(p: Project) -> Project:
        model = _ahp(p)
        judgements = _matrix_judgements(model, top, group, leaf)
        pair = {row, column}
        judgements[:] = [j for j in judgements if {j.row, j.column} != pair]
        judgements.append(PairwiseJudgement(row=row, column=column, value=value))
        return ps.set_ahp_model(p, model)

    _edit(file, output, change)


@ahp_app.command("remove")
def ahp_remove(
    file: FileArg,
    row: Annotated[str, typer.Argument(help="One item of the pair.")],
    column: Annotated[str, typer.Argument(help="The other item.")],
    top: TopOpt = False,
    group: GroupOpt = None,
    leaf: LeafOpt = None,
    output: OutOpt = None,
) -> None:
    """Remove one pairwise judgement, in either orientation."""

    def change(p: Project) -> Project:
        model = _ahp(p)
        judgements = _matrix_judgements(model, top, group, leaf)
        judgements[:] = [j for j in judgements if {j.row, j.column} != {row, column}]
        return ps.set_ahp_model(p, model)

    _edit(file, output, change)


@ahp_app.command("clear")
def ahp_clear(file: FileArg, output: OutOpt = None) -> None:
    """Remove every AHP judgement; the project returns to the lowest version it needs."""
    _edit(file, output, ps.clear_ahp_model)


@ahp_app.command("check")
def ahp_check(file: FileArg) -> None:
    """Every matrix's consistency ratio and most inconsistent triad, or what it still lacks."""
    project = _guard(lambda: repo.load(file))
    model = project.ahp or AhpModel()
    tree = _guard(project.tree)
    stated = {g.parent_id: g.judgements for g in model.criteria}
    on_leaf = {a.criterion_id: a.judgements for a in model.alternatives}
    matrices = [
        (f"criteria under {'top level' if g is None else g}", tree.child_ids(g), stated.get(g, []))
        for g in criteria_groups(tree)
    ] + [
        (f"alternatives under {leaf}", project.alternative_ids(), on_leaf.get(leaf, []))
        for leaf in tree.leaves()
    ]
    rows = []
    incomplete = 0
    for name, items, judgements in matrices:
        preview = svc.preview_ahp_matrix(items, judgements)
        if preview.analysis is None:
            incomplete += 1
            console.print(f"{name}: {escape(preview.issues[0].message)}")
            continue
        a = preview.analysis
        rows.append(
            (
                name,
                len(items),
                a.consistency_ratio,
                a.inconsistent,
                _triad_text(a.most_inconsistent_triad),
            )
        )
    if rows:
        console.print(_consistency_table(rows))
    if incomplete:
        console.print(f"[red]{incomplete} matrix(es) incomplete[/red]")
        raise typer.Exit(1)


# ---- feasibility requirements --------------------------------------------------------------------
def _replace_requirement(new: AnyRequirement) -> Callable[[Project], Project]:
    def change(p: Project) -> Project:
        listed = [r for r in (p.requirements or []) if r.id != new.id]
        at = next((k for k, r in enumerate(p.requirements or []) if r.id == new.id), len(listed))
        listed.insert(at, new)
        return ps.set_requirements(p, listed)

    return change


NameOpt = Annotated[str, typer.Option("--name", help="Shown in results and exports.")]
RationaleOpt = Annotated[str, typer.Option(help="Why the requirement is mandatory.")]


@requirement_app.command("bound")
def requirement_bound(
    file: FileArg,
    requirement_id: Annotated[str, typer.Argument(help="Stable requirement id.")],
    criterion: Annotated[str, typer.Argument(help="Numeric leaf criterion id.")],
    name: NameOpt,
    minimum: Annotated[float | None, typer.Option("--min", help="Lowest allowed value.")] = None,
    maximum: Annotated[float | None, typer.Option("--max", help="Highest allowed value.")] = None,
    exclusive_min: Annotated[
        bool, typer.Option("--exclusive-min", help="The minimum itself fails.")
    ] = False,
    exclusive_max: Annotated[
        bool, typer.Option("--exclusive-max", help="The maximum itself fails.")
    ] = False,
    unit: Annotated[
        str | None, typer.Option(help="The leaf's unit, stated; it is never converted.")
    ] = None,
    rationale: RationaleOpt = "",
    output: OutOpt = None,
) -> None:
    """State or replace a numeric bound on one leaf's measurement."""
    if minimum is None and maximum is None:
        _fail("give --min, --max or both")
    new = BoundRequirement(
        id=requirement_id,
        name=name,
        criterion_id=criterion,
        unit=unit,
        minimum=minimum,
        minimum_inclusive=not exclusive_min,
        maximum=maximum,
        maximum_inclusive=not exclusive_max,
        rationale=rationale,
    )
    _edit(file, output, _replace_requirement(new))


@requirement_app.command("labels")
def requirement_labels(
    file: FileArg,
    requirement_id: Annotated[str, typer.Argument(help="Stable requirement id.")],
    criterion: Annotated[str, typer.Argument(help="Labelled leaf criterion id.")],
    name: NameOpt,
    allow: Annotated[list[str] | None, typer.Option(help="An allowed label (repeat).")] = None,
    at_least: Annotated[
        str | None, typer.Option(help="Ordinal: this label and every label above it.")
    ] = None,
    at_most: Annotated[
        str | None, typer.Option(help="Ordinal: this label and every label below it.")
    ] = None,
    rationale: RationaleOpt = "",
    output: OutOpt = None,
) -> None:
    """State or replace one leaf's allowed labels; the ordinal helpers write the explicit set."""
    if bool(allow) + (at_least is not None) + (at_most is not None) != 1:
        _fail("give exactly one of --allow (repeat), --at-least or --at-most")
    allowed = list(allow or [])
    if at_least is not None or at_most is not None:
        project = _guard(lambda: repo.load(file))
        scale = _guard(lambda: project.tree().node(criterion)).scale
        if scale is None or scale.type is not ScaleType.ORDINAL:
            _fail("--at-least and --at-most need an ordinal leaf")
        label = at_least if at_least is not None else at_most
        if label not in scale.labels:
            _fail(f"{label!r} is not one of the scale's labels {scale.labels}")
        k = scale.labels.index(label)
        allowed = scale.labels[k:] if at_least is not None else scale.labels[: k + 1]
    new = LabelsRequirement(
        id=requirement_id, name=name, criterion_id=criterion, allowed=allowed, rationale=rationale
    )
    _edit(file, output, _replace_requirement(new))


@requirement_app.command("remove")
def requirement_remove(
    file: FileArg,
    requirement_id: Annotated[str, typer.Argument(help="Requirement id.")],
    output: OutOpt = None,
) -> None:
    """Remove one requirement."""
    _edit(
        file,
        output,
        lambda p: ps.set_requirements(
            p, [r for r in (p.requirements or []) if r.id != requirement_id]
        ),
    )


@requirement_app.command("clear")
def requirement_clear(file: FileArg, output: OutOpt = None) -> None:
    """Remove every requirement; the project returns to the lowest version it needs."""
    _edit(file, output, ps.clear_requirements)


@app.command("feasibility")
def feasibility_check(file: FileArg, output: OutOpt = None) -> None:
    """Pass, fail or unknown per alternative and requirement; rankings are not changed."""
    project = _guard(lambda: repo.load(file))
    result = _guard(lambda: feasibility.check_feasibility(project))
    console.print(f"[bold]{result.label}[/bold]")
    table = Table("alternative", "overall", *(escape(r.name) for r in result.requirements))
    for a in result.alternatives:
        table.add_row(escape(a.name), a.status, *(c.status for c in a.checks))
    console.print(table)
    names = {r.id: r.name for r in result.requirements}
    for a in result.alternatives:
        for c in a.checks:
            if c.status != "pass":
                where = f"{escape(a.name)}, {escape(names[c.requirement_id])}"
                console.print(f"{where}: {escape(c.reason)}")
    for d in result.diagnostics:
        console.print(f"[dim]{d.severity.value}: {escape(d.message)}[/dim]")
    if output:
        _guard(lambda: _save_result(result, output))
        console.print(f"feasibility written to [bold]{output}[/bold]")


# ---- editing commands ---------------------------------------------------------------------
@alt_app.command("add")
def alternative_add(
    file: FileArg,
    name: str,
    alt_id: Annotated[str | None, typer.Option("--id")] = None,
    output: OutOpt = None,
) -> None:
    """Add an alternative."""
    _edit(file, output, lambda p: ps.add_alternative(p, name, alt_id))


@alt_app.command("remove")
def alternative_remove(file: FileArg, alt_id: str, output: OutOpt = None) -> None:
    """Remove an alternative and its measurements."""
    _edit(file, output, lambda p: ps.remove_alternative(p, alt_id))


@crit_app.command("add")
def criterion_add(
    file: FileArg,
    name: str,
    parent: Annotated[str | None, typer.Option(help="Parent criterion id.")] = None,
    crit_id: Annotated[str | None, typer.Option("--id")] = None,
    position: Annotated[int | None, typer.Option(help="Position among siblings.")] = None,
    discard_leaf_data: Annotated[
        bool, typer.Option(help="Allow turning a measured leaf into a parent.")
    ] = False,
    output: OutOpt = None,
) -> None:
    """Add a criterion node."""
    _edit(
        file,
        output,
        lambda p: ps.add_criterion(
            p, name, parent, crit_id, position=position, discard_leaf_data=discard_leaf_data
        ),
    )


@crit_app.command("move")
def criterion_move(
    file: FileArg,
    crit_id: str,
    parent: Annotated[str | None, typer.Option(help="New parent id (omit for top level).")] = None,
    position: Annotated[int | None, typer.Option()] = None,
    output: OutOpt = None,
) -> None:
    """Move or reorder a criterion."""
    _edit(file, output, lambda p: ps.move_criterion(p, crit_id, parent, position))


@crit_app.command("remove")
def criterion_remove(file: FileArg, crit_id: str, output: OutOpt = None) -> None:
    """Remove a criterion and its subtree."""
    _edit(file, output, lambda p: ps.remove_criterion(p, crit_id))


@crit_app.command("set-scale")
def criterion_set_scale(
    file: FileArg,
    crit_id: str,
    scale_type: Annotated[ScaleType, typer.Option("--type")],
    lower: Annotated[float | None, typer.Option()] = None,
    upper: Annotated[float | None, typer.Option()] = None,
    unit: Annotated[str | None, typer.Option()] = None,
    anchor: Annotated[AnchorMode, typer.Option(help="fixed or local anchors.")] = AnchorMode.FIXED,
    labels: Annotated[str | None, typer.Option(help="Comma-separated, low to high.")] = None,
    output: OutOpt = None,
) -> None:
    """Define a leaf criterion's measurement scale."""
    scale = Scale(
        type=scale_type,
        lower=lower,
        upper=upper,
        unit=unit,
        anchor_mode=anchor,
        labels=[s.strip() for s in labels.split(",")] if labels else [],
    )
    _edit(file, output, lambda p: ps.set_scale(p, crit_id, scale))


@crit_app.command("set-value-function")
def criterion_set_vf(
    file: FileArg,
    crit_id: str,
    kind: Annotated[str, typer.Option(help="linear | piecewise | qualitative | direct_rating")],
    direction: Annotated[Direction, typer.Option()] = Direction.INCREASING,
    points: Annotated[str | None, typer.Option(help='"x:value,x:value,..."')] = None,
    mapping: Annotated[str | None, typer.Option(help='"label=value,label=value,..."')] = None,
    min_rating: Annotated[float, typer.Option()] = 0.0,
    max_rating: Annotated[float, typer.Option()] = 100.0,
    out_of_domain: Annotated[str, typer.Option(help="error | clamp")] = "error",
    output: OutOpt = None,
) -> None:
    """Define a leaf criterion's value function."""

    def build() -> ValueFunctionSpec:
        ood: Any = out_of_domain
        if kind == "linear":
            return LinearValueFunction(direction=direction, out_of_domain=ood)
        if kind == "piecewise":
            if not points:
                _fail("--points is required for piecewise")
            pts = [
                ControlPoint(x=float(a), value=float(b))
                for a, b in (item.split(":") for item in points.split(","))
            ]
            return PiecewiseLinearValueFunction(points=pts, out_of_domain=ood)
        if kind == "qualitative":
            if not mapping:
                _fail("--mapping is required for qualitative")
            m = {k.strip(): float(v) for k, v in (item.split("=") for item in mapping.split(","))}
            return QualitativeValueFunction(mapping=m)
        if kind == "direct_rating":
            return DirectRatingValueFunction(
                min_rating=min_rating, max_rating=max_rating, out_of_domain=ood
            )
        _fail(f"unknown value-function kind {kind!r}")

    _edit(file, output, lambda p: ps.set_value_function(p, crit_id, _guard(build)))


@app.command("weight")
def weight_set(
    file: FileArg,
    node_id: str,
    rating: float,
    profile: Annotated[str | None, typer.Option(help="Weight profile id.")] = None,
    output: OutOpt = None,
) -> None:
    """Set a swing rating for a criterion node (relative to its siblings)."""
    _edit(file, output, lambda p: ps.set_judgement(p, node_id, rating, profile))


@app.command("measure")
def measure_set(
    file: FileArg,
    alt_id: str,
    crit_id: str,
    value: str,
    output: OutOpt = None,
) -> None:
    """Record a measurement; numbers are parsed, anything else is kept as a label."""
    parsed: float | str
    try:
        parsed = float(value)
    except ValueError:
        parsed = value
    _edit(file, output, lambda p: ps.set_performance(p, alt_id, crit_id, parsed))


if __name__ == "__main__":  # pragma: no cover
    app()


@app.command()
def serve(
    store: Annotated[
        Path | None,
        typer.Option(help="Folder holding the project files (default ~/.mcda-studio/projects)."),
    ] = None,
    host: Annotated[
        str, typer.Option(help="Interface to bind. Keep it on loopback.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="TCP port.")] = 8765,
    frontend: Annotated[
        Path | None,
        typer.Option(help="Built frontend override (default: checkout, then bundled GUI)."),
    ] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the app in the default browser.")
    ] = False,
) -> None:
    """Run the local web application (API + editor). Install the api or dev extra first."""
    try:
        import uvicorn  # noqa: F401 (check optional runtime before importing the app)

        from mcda_studio.api import create_app
    except ImportError as exc:
        _fail(
            f"the API dependencies are not installed ({exc.name}). Reinstall the release wheel "
            "with the api extra: pipx install "
            "'/path/to/mcda_studio-<version>-py3-none-any.whl[api]' "
            "--force; or python -m pip install '/path/to/release.whl[api]'."
        )
    if host not in ("127.0.0.1", "localhost", "::1"):
        err_console.print(
            "[yellow]warning:[/yellow] the server has no authentication; binding to "
            f"{host!r} exposes your projects to the network."
        )
    from mcda_studio.startup import run_server

    try:
        application = create_app(store, frontend_dir=frontend)
        dist = application.state.frontend_dir
        if frontend is not None and (dist is None or not (dist / "index.html").is_file()):
            _fail(
                f"No frontend index.html in {frontend}; correct --frontend or reinstall the wheel."
            )
        if not any(getattr(r, "name", None) == "frontend" for r in application.routes):
            if open_browser:
                _fail(
                    "No GUI assets found. Reinstall the bundled wheel or build frontend/dist first."
                )
            err_console.print("[yellow]note:[/yellow] GUI assets missing; serving API only.")
        url_host = f"[{host}]" if ":" in host else host
        console.print(
            f"MCDA Studio at http://{url_host}:{port} (projects: {application.state.store.root})"
        )
        run_server(application, host, port, open_browser)
    except (OSError, ValueError, McdaError) as exc:
        _fail(str(exc))


# ---- library backup -----------------------------------------------------------------------
JsonOpt = Annotated[bool, typer.Option("--json", help="Print a machine-readable report.")]


def _report(summary: str, report: backups.BackupReport, as_json: bool) -> None:
    """Print the outcome; exit 3 when something was skipped or could not be fully checked."""
    if as_json:
        typer.echo(json.dumps({"result": summary, **report.to_json()}, indent=2))
    else:
        console.print(escape(summary))
        for name, reason in report.skipped:
            console.print(f"[yellow]skipped[/yellow] {escape(name)}: {escape(reason)}")
        for path, reason in report.unchecked:
            console.print(f"[yellow]not checked[/yellow] {escape(path)}: {escape(reason)}")
    if report.warnings:
        raise typer.Exit(3)


def _counts(report: backups.BackupReport) -> str:
    active = f"{report.active} active project file{'' if report.active == 1 else 's'}"
    return f"{active} and {report.deleted} deleted entr{'y' if report.deleted == 1 else 'ies'}"


@library_app.command("backup")
def library_backup(
    store: Annotated[Path, typer.Option(help="Library folder to back up (stop its server).")],
    to: Annotated[Path, typer.Option(help="New backup file; never overwritten.")],
    as_json: JsonOpt = False,
) -> None:
    """Archive a stopped library, including Recently deleted, with a checked manifest."""
    report = _guard(lambda: backups.create_backup(store, to))
    _report(f"backed up {_counts(report)} to {to}", report, as_json)


@library_app.command("verify")
def library_verify(
    archive: Annotated[Path, typer.Argument(help="Backup file to check.")],
    as_json: JsonOpt = False,
) -> None:
    """Check a backup's structure, sizes, hashes and fingerprints; writes nothing."""
    report = _guard(lambda: backups.verify_backup(archive))
    _report(f"verified {_counts(report)} in {archive}", report, as_json)


@library_app.command("restore")
def library_restore(
    archive: Annotated[Path, typer.Argument(help="Backup file to restore.")],
    to: Annotated[Path, typer.Option(help="New library folder; must not exist yet.")],
    as_json: JsonOpt = False,
) -> None:
    """Verify a backup, then restore it into a new library folder."""
    report = _guard(lambda: backups.restore_backup(archive, to))
    _report(
        f"restored {_counts(report)} to {to}; open it with: mcda serve --store {to}",
        report,
        as_json,
    )


# Local external proposals are a separate sidecar workflow, never a project edit.
proposals_app = typer.Typer(
    help="Import, compare and explicitly review local external proposals.", no_args_is_help=True
)
app.add_typer(proposals_app, name="proposals")


def _proposal_workspace(project: Project, file: Path) -> ExternalProposals:
    from mcda_studio.services import proposal_import_service

    return proposal_import_service.parse(project, proposal_import_service.read_local(file))


@proposals_app.command("import")
def proposal_import(
    file: FileArg,
    intake: FileArg,
    output: Annotated[Path, typer.Option("--output", "-o")],
    format: Annotated[Literal["json", "csv"], typer.Option()] = "json",
    registries: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Normalize a complete local file into a new sidecar; structural errors refuse every row."""
    from mcda_studio.services import proposal_import_service

    try:
        project = repo.load(file)
        workspace = proposal_import_service.parse(
            project,
            proposal_import_service.read_local(intake),
            format,
            proposal_import_service.read_local(registries) if registries else None,
        )
        _new_file(output, to_json_text(workspace))
    except (McdaError, OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo("Proposal workspace created.")


@proposals_app.command("inspect")
@proposals_app.command("preview")
def proposal_inspect(
    file: FileArg,
    workspace: FileArg,
    comparison_target: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Inspect every original, review, comparison and proposed measurement change."""
    from mcda_studio.services import proposal_service

    try:
        project = repo.load(file)
        report = proposal_service.inspect(
            project, _proposal_workspace(project, workspace), comparison_target
        )
    except (McdaError, OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(to_json_text(report))


@proposals_app.command("review")
def proposal_review(
    file: FileArg,
    workspace: FileArg,
    events: FileArg,
    output: Annotated[Path, typer.Option("--output", "-o")],
    bulk: Annotated[bool, typer.Option()] = False,
    confirm_selection: Annotated[str | None, typer.Option()] = None,
    comparison_target: Annotated[str | None, typer.Option()] = None,
) -> None:
    """List every selected proposal first; repeat with its confirmation digest to write reviews."""
    from pydantic import TypeAdapter

    from mcda_studio.domain.external_proposals import ProposalReview
    from mcda_studio.services import proposal_import_service, proposal_service

    try:
        project = repo.load(file)
        document = _proposal_workspace(project, workspace)
        event_text = proposal_import_service.read_local(events)
        proposal_import_service.strict_json(event_text)
        selected = TypeAdapter(list[ProposalReview]).validate_json(event_text)
        current = proposal_service.inspect(project, document, comparison_target)
        candidate = proposal_service.review(
            project,
            document,
            selected,
            current.review_digest,
            document.digest,
            bulk,
            comparison_target,
        )
        by_id = {p.id: p for p in document.intake.proposals}
        affected = [
            {
                "proposal_id": e.proposal_id,
                "original": by_id[e.proposal_id].model_dump(mode="json"),
                "review": e.review.model_dump(mode="json"),
            }
            for e in selected
        ]
        confirmation = evidence._digest(
            {
                "project": project.fingerprint(),
                "workspace": document.digest,
                "review": current.review_digest,
                "events": affected,
                "bulk": bulk,
            }
        )
        if confirm_selection is None:
            typer.echo(
                json.dumps(
                    {
                        "confirmation_digest": confirmation,
                        "affected": affected,
                        "action": "Repeat with --confirm-selection DIGEST to write reviews.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if confirm_selection != confirmation:
            raise StaleRevisionError(
                "Proposal selection changed; preview every affected item again."
            )
        _new_file(output, to_json_text(candidate.workspace))
    except (McdaError, OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo("Confirmed proposal reviews created.")


@proposals_app.command("compile")
def proposal_compile(
    file: FileArg,
    workspace: FileArg,
    review_digest: Annotated[str, typer.Option()],
    workspace_digest: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option("--output", "-o")],
    comparison_target: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Compile an acknowledged preview into a new bundle containing its separate project copy."""
    from mcda_studio.services import proposal_service

    try:
        project = repo.load(file)
        bundle = proposal_service.compile_bundle(
            project,
            _proposal_workspace(project, workspace),
            review_digest,
            workspace_digest,
            comparison_target,
        )
        _new_file(output, to_json_text(bundle))
    except (McdaError, OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo("Proposal compilation bundle created; its evidence.project is the separate copy.")


@proposals_app.command("verify")
def proposal_verify(file: FileArg) -> None:
    """Replay a workspace or reconstruct its complete compilation without writing anything."""
    from mcda_studio.domain.external_proposals import ExternalProposals
    from mcda_studio.services import proposal_import_service, proposal_service

    try:
        raw = proposal_import_service.strict_json(proposal_import_service.read_local(file))
        if isinstance(raw, dict) and raw.get("artifact_kind") == "proposal_compilation":
            proposal_service.verify(
                proposal_service.ProposalCompilation.model_validate_json(json.dumps(raw))
            )
        else:
            document = ExternalProposals.model_validate_json(json.dumps(raw))
            proposal_service._replay(document)
            if document.source_project is not None:
                proposal_service.inspect(document.source_project, document)
    except (McdaError, OSError, UnicodeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo("Proposal artifact verified.")
