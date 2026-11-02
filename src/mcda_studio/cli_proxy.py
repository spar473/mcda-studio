"""Local file counterparts of disclosed-proxy review and paired analysis."""

from pathlib import Path
from typing import Annotated

import typer

from mcda_studio.cli_models import _call, _write
from mcda_studio.domain.proxy_criterion import ProxyCriterionPlan, ProxyOperation, ProxyPlanState
from mcda_studio.services import proxy_criterion_service as proxy
from mcda_studio.services import proxy_plan_service as plans
from mcda_studio.services.proposal_import_service import read_local

proxy_app = typer.Typer(
    help="Explicit disclosed-proxy plans and complete with/without pairs.", no_args_is_help=True
)


@proxy_app.command("start")
def start(state: Path, output: Annotated[Path, typer.Option("--output", "-o")]) -> None:
    _call(
        lambda: _write(output, plans.start(ProxyPlanState.model_validate_json(read_local(state))))
    )


@proxy_app.command("revise")
def revise(
    plan: Path,
    operation: Path,
    expected_digest: str,
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    _call(
        lambda: _write(
            output,
            plans.revise(
                ProxyCriterionPlan.model_validate_json(read_local(plan)),
                ProxyOperation.model_validate_json(read_local(operation)),
                expected_digest,
            ),
        )
    )


@proxy_app.command("inspect")
@proxy_app.command("preview-pair")
def inspect(
    inputs: Path, output: Annotated[Path | None, typer.Option("--output", "-o")] = None
) -> None:
    _call(
        lambda: _write(
            output, proxy.inspect(proxy.ProxyInputs.model_validate_json(read_local(inputs)))
        )
    )


@proxy_app.command("run-pair")
def run(inputs: Path, output: Annotated[Path, typer.Option("--output", "-o")]) -> None:
    _call(
        lambda: _write(
            output, proxy.run_pair(proxy.ProxyPairRequest.model_validate_json(read_local(inputs)))
        )
    )


@proxy_app.command("verify")
def verify(bundle: Path) -> None:
    import json

    _call(lambda: _write(None, proxy.verify(json.loads(read_local(bundle)))))
