"""Independent plain-Python oracle for the method comparison view. It never imports mcda_studio.

From each method's own ``/evaluate`` body (a JSON dict), it recomputes what the comparison must
show: each alternative's rank, quantity and class in that method's own terms, each method's
leaders, whether the leaders agree, the leader groups, the sorting/SMAA-2 class agreement, and
which methods need a reason. It adds, averages or aggregates nothing.
"""

from typing import Any

TOL = 1e-12
Body = dict[str, Any]


def competition(values: dict[str, float]) -> dict[str, int]:
    return {a: 1 + sum(1 for v in values.values() if v > values[a] + TOL) for a in values}


def cells(method: str, body: Body) -> dict[str, dict[str, Any]]:
    """Per alternative: rank, quantity and class, in the method's own terms."""
    if method == "smaa2":
        firsts = {a["alternative_id"]: a["ranks"][0]["frequency"] for a in body["acceptability"]}
        ranks = competition(firsts)
        classes = sorted(body["classes"], key=lambda c: c["rank"])
        out = {}
        for a in body["acceptability"]:
            modal = None
            for c in classes:  # better classes first, so ties go to the better class
                share = a["classes"][c["class_id"]]["frequency"]
                if modal is None or share > modal[1]:
                    modal = (c["class_id"], share)
            out[a["alternative_id"]] = {
                "rank": ranks[a["alternative_id"]],
                "quantity": a["ranks"][0]["frequency"],
                "class": modal[0] if modal else None,
            }
        return out
    if method == "promethee2":
        return {
            f["alternative_id"]: {"rank": f["rank"], "quantity": f["net_flow"], "class": None}
            for f in body["flows"]
        }
    if method == "ahp":
        return {
            a["alternative_id"]: {"rank": a["rank"], "quantity": a["priority"], "class": None}
            for a in body["alternatives"]
        }
    assigned = {a["alternative_id"]: a["class_id"] for a in body.get("assignments", [])}
    return {
        a["alternative_id"]: {
            "rank": a["rank"],
            "quantity": a["overall_value"],
            "class": assigned.get(a["alternative_id"]),
        }
        for a in body["alternatives"]
    }


def leaders(method: str, body: Body) -> list[str]:
    if method == "smaa2":
        return [body["leader_id"]]
    return [r["alternative_id"] for r in body["ranking"] if r["rank"] == 1]


def agreement(bodies: dict[str, Body]) -> dict[str, Any]:
    """Over the methods that ran, in the given order."""
    led = {m: leaders(m, b) for m, b in bodies.items()}
    agree = None
    if len(led) >= 2:
        first = set(next(iter(led.values())))
        agree = all(len(v) == 1 and set(v) == first for v in led.values())
    groups: dict[tuple[str, ...], list[str]] = {}
    for m, v in led.items():
        groups.setdefault(tuple(sorted(v)), []).append(m)
    classes = []
    if "mavt_sorting" in bodies and "smaa2" in bodies and bodies["smaa2"]["classes"]:
        sorting = cells("mavt_sorting", bodies["mavt_sorting"])
        smaa = cells("smaa2", bodies["smaa2"])  # in the project's order, as the acceptabilities are
        classes = [(a, sorting[a]["class"], smaa[a]["class"]) for a in smaa]
    reasons = []
    if "mavt" in led:
        reasons = [m for m in led if m != "mavt" and set(led[m]) != set(led["mavt"])]
    return {"agree": agree, "groups": groups, "classes": classes, "reasons": reasons}
