"""End-to-end: create -> modify -> save -> load -> evaluate, via API, CLI and a fresh process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from mcda_studio import cli
from mcda_studio.cli import app
from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.preferences import Scenario
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.validation import validate_project
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository
from mcda_studio.storage.library_lock import LibraryOwnership

ROOT = Path(__file__).parents[2]
SUPPLIER = ROOT / "examples" / "supplier_selection" / "project.json"
repo = JsonProjectRepository()
runner = CliRunner()


def flat(text: str) -> str:
    """CLI output with Rich's line wrapping undone, so a phrase matches at any terminal width."""
    return " ".join(text.split())


@pytest.fixture
def wide_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render CLI tables at a fixed width. A narrow terminal truncates table cells ("batte…"), which
    no text matching can undo; tests that read cells must not depend on the terminal's width."""
    monkeypatch.setattr(cli, "console", Console(width=160))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=160))


def build_by_api() -> "ps.Project":  # noqa: UP037
    p = ps.new_project("Laptop choice")
    for name in ("Alpha", "Beta", "Gamma"):
        p = ps.add_alternative(p, name)
    p = ps.add_criterion(p, "Money", crit_id="money")
    p = ps.add_criterion(
        p,
        "Price",
        "money",
        "price",
        scale=Scale(type=ScaleType.RATIO, unit="NZD", lower=800, upper=3000),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Battery",
        crit_id="battery",
        scale=Scale(type=ScaleType.RATIO, unit="h", lower=4, upper=20),
        value_function=LinearValueFunction(),
    )
    for alt, price, battery in (("alpha", 1200, 12), ("beta", 2400, 18), ("gamma", 900, 6)):
        p = ps.set_performance(p, alt, "price", float(price))
        p = ps.set_performance(p, alt, "battery", float(battery))
    p = ps.set_judgement(p, "money", 100.0)
    p = ps.set_judgement(p, "battery", 70.0)
    return p


def test_create_modify_save_load_evaluate(tmp_path: Path) -> None:
    p = build_by_api()
    assert validate_project(p).ok
    first = svc.evaluate_project(p)
    path = repo.save(p, tmp_path / "laptops.json")

    reopened = repo.load(path)
    assert svc.evaluate_project(reopened) == first

    edited = ps.add_alternative(reopened, "Delta")
    edited = ps.set_performance(
        ps.set_performance(edited, "delta", "price", 1500.0), "delta", "battery", 16.0
    )
    second = svc.evaluate_project(edited)
    assert len(second.ranking) == 4
    assert len(first.ranking) == 3  # earlier result untouched by later edits
    assert repo.load(path) == p  # file on disk untouched until saved


def test_a_completely_different_problem_needs_no_code_changes() -> None:
    """Two structurally different models run through the same engine."""
    supplier = repo.load(SUPPLIER)
    laptops = build_by_api()
    a, b = svc.evaluate_project(supplier), svc.evaluate_project(laptops)
    assert len(a.ranking) == 5 and len(b.ranking) == 3
    assert len(a.leaf_order) == 8 and len(b.leaf_order) == 2  # type: ignore[attr-defined]


def test_fresh_process_reproduces_identical_results(tmp_path: Path) -> None:
    """Save, terminate Python, reopen in a brand-new interpreter, reproduce the same analysis."""
    p = repo.load(SUPPLIER)
    here = svc.evaluate_project(p)
    out = tmp_path / "fresh.json"
    proc = subprocess.run(
        [sys.executable, "-m", "mcda_studio.cli", "evaluate", str(SUPPLIER), "-o", str(out)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text()) == json.loads(here.model_dump_json())


def test_cli_builds_a_model_from_scratch(tmp_path: Path) -> None:
    f = str(tmp_path / "m.json")

    def run(*args: str, ok: bool = True) -> str:
        r = runner.invoke(app, list(args))
        assert (r.exit_code == 0) == ok, r.output
        return r.output

    run("new", "CLI model", "-o", f)
    run("validate", f, ok=False)  # a blank project is incomplete
    for name in ("Red", "Blue", "Green"):
        run("alternative", "add", f, name)
    run("criterion", "add", f, "Speed", "--id", "speed")
    run("criterion", "add", f, "Looks", "--id", "looks")
    run("criterion", "set-scale", f, "speed", "--type", "ratio", "--lower", "0", "--upper", "100")
    run("criterion", "set-value-function", f, "speed", "--kind", "linear")
    run("criterion", "set-scale", f, "looks", "--type", "ordinal", "--labels", "meh,ok,great")
    run(
        "criterion",
        "set-value-function",
        f,
        "looks",
        "--kind",
        "qualitative",
        "--mapping",
        "meh=0,ok=0.4,great=1",
    )
    for alt, speed, looks in (("red", "40", "great"), ("blue", "90", "meh"), ("green", "70", "ok")):
        run("measure", f, alt, "speed", speed)
        run("measure", f, alt, "looks", looks)
    run("validate", f, ok=False)  # swing ratings still missing
    run("weight", f, "speed", "100")
    run("weight", f, "looks", "60")
    assert "valid" in run("validate", f)
    out = str(tmp_path / "r.json")
    table = run("evaluate", f, "-o", out)
    assert "Blue" in table and json.loads(Path(out).read_text())["ranking"]
    assert "speed" in run("sensitivity", f, "--criterion", "speed")
    assert "looks" in run("sensitivity", f, "--all")
    run("sensitivity", f, ok=False)  # needs --criterion or --all
    run("duplicate", f, "-o", str(tmp_path / "copy.json"), "--title", "Copy")
    assert repo.load(tmp_path / "copy.json").title == "Copy"
    run("criterion", "move", f, "looks", "--position", "0")
    run("criterion", "remove", f, "looks")
    run("alternative", "remove", f, "green")
    assert "Blue" in run("evaluate", f)


def test_cli_templates_and_error_reporting(tmp_path: Path) -> None:
    assert "supplier-selection" in runner.invoke(app, ["templates"]).output
    f = str(tmp_path / "t.json")
    assert (
        runner.invoke(app, ["new", "T", "-o", f, "--template", "supplier-selection"]).exit_code == 0
    )
    r = runner.invoke(app, ["new", "T", "-o", f, "--template", "nope"])
    assert r.exit_code == 1 and "unknown template" in flat(r.output)
    r = runner.invoke(app, ["evaluate", f])  # incomplete project must be refused, not guessed at
    assert r.exit_code == 1 and "validation error" in flat(r.output)
    r = runner.invoke(app, ["evaluate", str(tmp_path / "missing.json")])
    assert r.exit_code == 1 and "not found" in flat(r.output)


def test_cli_evaluate_json_and_scenarios(wide_tables: None) -> None:
    r = runner.invoke(app, ["evaluate", str(SUPPLIER), "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["method"] == "mavt" and len(data["ranking"]) == 5
    r = runner.invoke(app, ["evaluate", str(SUPPLIER), "--profile", "cost_focus", "--json"])
    assert json.loads(r.output)["weight_profile_id"] == "cost_focus"
    r = runner.invoke(app, ["compare", str(SUPPLIER)])
    assert r.exit_code == 0 and "baseline" in r.output


def test_scenarios_and_profiles_change_results_without_touching_the_baseline() -> None:
    p = repo.load(SUPPLIER)
    base = svc.evaluate_project(p)
    cost = svc.evaluate_project(
        p, p.analysis.model_copy(update={"weight_profile_id": "cost_focus"})
    )
    assert [r.value for r in cost.ranking] != [r.value for r in base.ranking]
    assert svc.evaluate_project(p) == base


def test_unknown_method_is_reported() -> None:
    from mcda_studio.domain.errors import UnknownReferenceError

    p = build_by_api()
    cfg = p.analysis.model_copy(update={"method": "promethee"})
    with pytest.raises(UnknownReferenceError, match="available: ahp, mavt, "):
        svc.evaluate_project(p, cfg)


def test_scenario_added_through_service_is_persisted(tmp_path: Path) -> None:
    p = ps.add_scenario(
        build_by_api(),
        Scenario(
            id="flat", name="flat", value_function_overrides={"battery": LinearValueFunction()}
        ),
    )
    q = repo.load(repo.save(p, tmp_path / "s.json"))
    assert (
        q.scenarios[0].id == "flat" and svc.compare_scenarios(q).scenarios[0].scenario_id == "flat"
    )


def test_sensitivity_all_says_which_nodes_it_could_not_vary(
    tmp_path: Path, wide_tables: None
) -> None:
    """'price' is the only child of 'money': its local weight is fixed at 1, so it cannot be varied.
    The CLI must say so instead of silently leaving it out of the table."""
    f = tmp_path / "m.json"
    repo.save(build_by_api(), f)
    out = flat(runner.invoke(app, ["sensitivity", str(f), "--all"]).output)
    assert "not analysed" in out and "price" in out.split("not analysed", 1)[1]
    assert "battery" in out.split("not analysed", 1)[0]  # varied nodes stay in the table
    # exporting everything is unaffected
    assert (
        runner.invoke(
            app, ["sensitivity", str(f), "--all", "-o", str(tmp_path / "s.json")]
        ).exit_code
        == 0
    )


@pytest.mark.parametrize(
    "args",
    [
        ["evaluate", str(SUPPLIER), "-o", "OUT"],
        ["sensitivity", str(SUPPLIER), "--all", "-o", "OUT"],
    ],
    ids=["evaluate", "sensitivity-all"],
)
def test_cli_result_outputs_respect_library_ownership(tmp_path: Path, args: list[str]) -> None:
    """Every result file written into a managed library needs its lock, ``--all`` exports too."""
    library = tmp_path / "library"
    library.mkdir()
    out = library / "result.json"
    argv = [str(out) if a == "OUT" else a for a in args]
    with LibraryOwnership(library):
        refused = runner.invoke(app, argv)
        assert refused.exit_code == 1
        assert "owned by another process" in flat(refused.output)
        assert not out.exists()
    allowed = runner.invoke(app, argv)  # the same write succeeds once the owner has stopped
    assert allowed.exit_code == 0 and out.is_file()


def test_cli_prints_bracketed_paths_and_messages_literally(
    tmp_path: Path, wide_tables: None
) -> None:
    """Regression (found in Stage 2A): Rich treated ``[cost]`` in ``criteria[cost]`` as markup and
    silently dropped it, so the validation table showed the wrong location."""
    p = ps.add_criterion(
        ps.add_alternative(ps.new_project("Half done"), "A"), "Cost", crit_id="cost"
    )
    path = tmp_path / "half.json"
    repo.save(p, path)
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "criteria[cost]" in flat(result.output)

    bad = runner.invoke(app, ["evaluate", str(path)])
    assert bad.exit_code == 1
    assert "criteria[cost]" in flat(bad.output)
