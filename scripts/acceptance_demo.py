"""Stage 1 sign-off demonstration (steps 2-6 of the acceptance list).

Run in a clean environment:  python scripts/acceptance_demo.py
Step 7 (the full test suite) is `python -m pytest`.

If examples/nz_deeptech_vc/project.json exists it is reproduced against the documented base case;
otherwise that step is reported as SKIPPED (never faked) and the supplier-selection example
stands in so the rest of the demonstration still runs.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from mcda_studio.domain.criteria import Direction, LinearValueFunction, QualitativeValueFunction
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).resolve().parents[1]
repo = JsonProjectRepository()


def step(n: int, text: str) -> None:
    print(f"\n[{n}] {text}")


def main() -> int:
    step(2, "Load the NZ deep-tech VC reference project and reproduce its documented results")
    ref = ROOT / "examples" / "nz_deeptech_vc" / "project.json"
    if ref.exists():
        result = svc.evaluate_project(repo.load(ref))
        print("   ", [(r.name, round(r.value, 3)) for r in result.ranking])
        print("    compare with 0.723 / 0.660 / 0.599 / 0.573 (the regression tests do this)")
    else:
        print("    SKIPPED: examples/nz_deeptech_vc/project.json not supplied (see its README)")
        result = svc.evaluate_project(
            repo.load(ROOT / "examples" / "supplier_selection" / "project.json")
        )
        print(
            "    stand-in (supplier example):",
            [(r.name, round(r.value, 4)) for r in result.ranking],
        )

    step(3, "Close it and create a blank, unrelated decision problem")
    p = ps.new_project("Pick a holiday destination")

    step(4, "Build an arbitrary value tree with new alternatives, scales and weights")
    for name in ("Lisbon", "Kyoto", "Queenstown", "Reykjavik"):
        p = ps.add_alternative(p, name)
    p = ps.add_criterion(p, "Money", crit_id="money")
    p = ps.add_criterion(
        p,
        "Flights",
        "money",
        "flights",
        scale=Scale(type=ScaleType.RATIO, unit="NZD", lower=300, upper=3000),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Daily cost",
        "money",
        "daily",
        scale=Scale(type=ScaleType.RATIO, unit="NZD/day", lower=80, upper=400),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(p, "Experience", crit_id="experience")
    p = ps.add_criterion(
        p,
        "Scenery",
        "experience",
        "scenery",
        scale=Scale(type=ScaleType.ORDINAL, labels=["ok", "good", "stunning"]),
        value_function=QualitativeValueFunction(mapping={"ok": 0.0, "good": 0.5, "stunning": 1.0}),
    )
    p = ps.add_criterion(
        p,
        "Food",
        "experience",
        "food",
        scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=10),
        value_function=LinearValueFunction(),
    )
    data = {
        "lisbon": (2900, 140, "good", 9),
        "kyoto": (1700, 220, "stunning", 10),
        "queenstown": (600, 300, "stunning", 7),
        "reykjavik": (2600, 390, "good", 6),
    }
    for alt, (fl, dc, sc, fd) in data.items():
        p = ps.set_performance(p, alt, "flights", float(fl))
        p = ps.set_performance(p, alt, "daily", float(dc))
        p = ps.set_performance(p, alt, "scenery", sc)
        p = ps.set_performance(p, alt, "food", float(fd))
    for node, rating in {
        "money": 80,
        "experience": 100,
        "flights": 100,
        "daily": 70,
        "scenery": 100,
        "food": 60,
    }.items():
        p = ps.set_judgement(p, node, float(rating))

    step(5, "Calculate rankings and perform a sensitivity analysis")
    before = svc.evaluate_project(p)
    print("   ", [(r.name, round(r.value, 4)) for r in before.ranking])
    sens = svc.sensitivity(p, "money")
    up, down = sens.first_winner_change_up, sens.first_winner_change_down
    print(
        f"    money weight {sens.base_weight:.4f}; winner change up: "
        f"{up and (up.to_winner, round(up.weight, 4))}; down: "
        f"{down and (down.to_winner, round(down.weight, 4))}"
    )

    step(6, "Save, close, reopen in a NEW Python process and reproduce the same results")
    with tempfile.TemporaryDirectory() as tmp:
        path = repo.save(p, Path(tmp) / "holiday.json")
        out = Path(tmp) / "fresh_result.json"
        subprocess.run(
            [sys.executable, "-m", "mcda_studio.cli", "evaluate", str(path), "-o", str(out)],
            check=True,
            capture_output=True,
        )
        identical = json.loads(out.read_text()) == json.loads(before.model_dump_json())
        print("    identical results after reload in a fresh process:", identical)
        assert identical, "results differ after reload"
    print("\nDemonstration finished. Step 7: run `python -m pytest`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
