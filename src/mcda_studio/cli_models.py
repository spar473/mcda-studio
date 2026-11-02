"""File-based counterparts of stateless model and starter operations."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from mcda_studio.domain.errors import McdaError
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.model_comparison import ModelComparison, ModelOutputSpec
from mcda_studio.domain.project import Project
from mcda_studio.domain.starter_templates import StarterInstantiationRequest, StarterMaterialization
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import starter_template_service as starters
from mcda_studio.services.proposal_import_service import read_local

starter_app = typer.Typer(
    help="Local hash-checked starter materials and lineage.", no_args_is_help=True
)
model_app = typer.Typer(
    help="Separate model outputs and explicit target selection.", no_args_is_help=True
)


def _write(output: Path | None, value: Any) -> None:
    text = (
        json.dumps(
            value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
    if output is None:
        typer.echo(text, nl=False)
    else:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(text)


def _call(action: Any) -> None:
    try:
        action()
    except (McdaError, ValidationError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


@starter_app.command("list")
def list_starters(output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    _call(lambda: _write(output, [t.model_dump(mode="json") for t in starters.list_templates()]))


@starter_app.command("instantiate")
def instantiate_starter(
    request: Path, output: Annotated[Path, typer.Option("--output", "-o")]
) -> None:
    _call(
        lambda: _write(
            output,
            starters.instantiate(
                StarterInstantiationRequest.model_validate_json(read_local(request))
            ),
        )
    )


@starter_app.command("verify")
def verify_starter(materials: Path) -> None:
    _call(
        lambda: _write(
            None, starters.verify(StarterMaterialization.model_validate_json(read_local(materials)))
        )
    )


@starter_app.command("archive")
def archive_starter(
    materials: Path, output: Annotated[Path, typer.Option("--output", "-o")]
) -> None:
    def action() -> None:
        result = starters.archive(StarterMaterialization.model_validate_json(read_local(materials)))
        with output.open("xb") as handle:
            handle.write(result)

    _call(action)


@model_app.command("inspect")
def inspect_models(
    project: Path,
    comparison: Path,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    _call(
        lambda: _write(
            output,
            comparisons.inspect(
                Project.model_validate_json(read_local(project)),
                ModelComparison.model_validate_json(read_local(comparison)),
            ),
        )
    )


@model_app.command("run-output")
def run_model_output(
    project: Path, specification: Path, output: Annotated[Path, typer.Option("--output", "-o")]
) -> None:
    _call(
        lambda: _write(
            output,
            checks.run_output(
                Project.model_validate_json(read_local(project)),
                ModelOutputSpec.model_validate_json(read_local(specification)),
            ),
        )
    )


@model_app.command("review")
def review_models(
    project: Path,
    comparison: Path,
    review_file: Path,
    expected_review_digest: str,
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    _call(
        lambda: _write(
            output,
            comparisons.review(
                Project.model_validate_json(read_local(project)),
                ModelComparison.model_validate_json(read_local(comparison)),
                Review.model_validate_json(read_local(review_file)),
                expected_review_digest,
            ).comparison,
        )
    )


@model_app.command("compile")
def compile_models(
    project: Path,
    comparison: Path,
    selection: Path,
    expected_review_digest: str,
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    _call(
        lambda: _write(
            output,
            comparisons.compile_selection(
                Project.model_validate_json(read_local(project)),
                ModelComparison.model_validate_json(read_local(comparison)),
                comparisons.ModelTargetSelection.model_validate_json(read_local(selection)),
                expected_review_digest,
            ),
        )
    )


@model_app.command("verify")
def verify_models(bundle: Path) -> None:
    _call(
        lambda: _write(
            None,
            comparisons.verify(
                comparisons.ModelComparisonCompilation.model_validate_json(read_local(bundle))
            ),
        )
    )


@model_app.command("run-checked")
def run_checked_model(
    project: Path,
    model: Path,
    uncertainty: Path,
    checks_file: Path,
    parameters: Path,
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    from mcda_studio.domain.derived import DerivedModel
    from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
    from mcda_studio.domain.model_comparison import ModelChecks
    from mcda_studio.services import checked_factor_service, factor_analysis_service

    _call(
        lambda: _write(
            output,
            checked_factor_service.run(
                Project.model_validate_json(read_local(project)),
                DerivedModel.model_validate_json(read_local(model)),
                FactorUncertaintyModel.model_validate_json(read_local(uncertainty)),
                ModelChecks.model_validate_json(read_local(checks_file)),
                factor_analysis_service.FactorRunParameters.model_validate_json(
                    read_local(parameters)
                ),
            ),
        )
    )


@model_app.command("verify-checked")
def verify_checked_model(record: Path) -> None:
    from mcda_studio.services import checked_factor_service

    _call(
        lambda: _write(
            None,
            checked_factor_service.verify(
                checked_factor_service.CheckedFactorRun.model_validate_json(read_local(record))
            ),
        )
    )


@model_app.command("verify-output")
def verify_model_output(record: Path) -> None:
    _call(
        lambda: _write(
            None,
            checks.verify_output(checks.ModelOutputRun.model_validate_json(read_local(record))),
        )
    )
