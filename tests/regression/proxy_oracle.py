"""Independent additive proxy pairs, using exact rationals and derived rounding bounds.

The shared bound helper derives the standard binary64 model (Higham, 2nd ed., §2.2).
Positive-term summation uses conservative successive-addition bounds; these cover the
correctly rounded positive sum as well. No application imports or fixed error tolerance.
"""

from fractions import Fraction

from regression.rounding_oracle import Bounded


def values(project, profile_id):
    profile = next(p for p in project["weight_profiles"] if p["id"] == profile_id)
    nodes = project["criteria"]
    children = {}
    for node in nodes:
        children.setdefault(node["parent_id"], []).append(node)
    leaves = [node for node in nodes if node["id"] not in children]
    weights = {}

    def descend(parent, share):
        siblings = children.get(parent, [])
        ratings = {
            node["id"]: Bounded.input(
                str(profile["judgements"].get(node["id"], 1 if len(siblings) == 1 else None))
            )
            for node in siblings
        }
        total = sum(ratings.values(), Bounded.input("0"))
        for node in siblings:
            weight = share * (ratings[node["id"]] / total)
            if node["id"] in children:
                descend(node["id"], weight)
            else:
                weights[node["id"]] = weight

    descend(None, Bounded.input("1"))
    measurements = {
        (p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]
    }
    result = {}
    for alternative in project["alternatives"]:
        terms = []
        for c in leaves:
            scale = c["scale"]
            x = Bounded.input(str(measurements[alternative["id"], c["id"]]))
            lo, hi = Bounded.input(str(scale["lower"])), Bounded.input(str(scale["upper"]))
            partial = (x - lo) / (hi - lo)
            terms.append(partial * weights[c["id"]])
        result[alternative["id"]] = sum(terms, Bounded.input("0"))
    return result


def classes(exact_values, bands):
    # The existing sorting rule explicitly declares this boundary tolerance.
    tolerance = Fraction("0.000000000001")
    return {
        id: next(
            c["id"]
            for c in bands
            if c["lower_boundary"] is None
            or value + tolerance >= Fraction(str(c["lower_boundary"]))
        )
        for id, value in exact_values.items()
    }


def projects(inputs):
    """Materialize the pair independently from declared inputs, never from engine outputs.

    In particular the reviewed proposal is the numeric oracle input: a wrong identity
    formula must not be allowed to redefine the measurement the oracle considers correct.
    Confidence, generated project IDs and digests have no mathematical role here.
    """
    from copy import deepcopy

    baseline = deepcopy(inputs["project"])
    state = deepcopy(inputs["plan"]["initial"])
    for revision in inputs["plan"]["revisions"]:
        if revision["operation"]["kind"] == "edit":
            state = deepcopy(revision["operation"]["state"])
    with_proxy = deepcopy(baseline)
    removed = set()
    for overlap in state["overlaps"]:
        if overlap["resolution"] != "remove_criterion":
            continue
        removed.update(overlap["remove_criterion_ids"])
    while True:
        more = {c["id"] for c in with_proxy["criteria"] if c["parent_id"] in removed}
        if more <= removed:
            break
        removed.update(more)
    with_proxy["criteria"] = [c for c in with_proxy["criteria"] if c["id"] not in removed]
    with_proxy["performances"] = [
        p for p in with_proxy["performances"] if p["criterion_id"] not in removed
    ]
    for profile in with_proxy["weight_profiles"]:
        profile["judgements"] = {
            key: value for key, value in profile["judgements"].items() if key not in removed
        }
        if profile["id"] in state["swing_ratings"]:
            profile["judgements"][state["criterion"]["id"]] = state["swing_ratings"][profile["id"]]
    for scenario in with_proxy["scenarios"]:
        scenario["value_function_overrides"] = {
            key: value
            for key, value in scenario["value_function_overrides"].items()
            if key not in removed
        }
    with_proxy["criteria"].append(deepcopy(state["criterion"]))
    workspace = inputs["scores"]
    latest = {event["proposal_id"]: event["review"] for event in workspace["reviews"]}
    scores = {}
    for proposal in workspace["intake"]["proposals"]:
        review = latest.get(proposal["id"])
        if (
            proposal["subject"]["criterion_id"] != state["criterion"]["id"]
            or review is None
            or review["status"] not in {"accepted", "corrected"}
        ):
            continue
        payload = (
            review["corrected_payload"] if review["status"] == "corrected" else proposal["payload"]
        )
        alternative = proposal["subject"]["alternative_id"]
        if payload["kind"] != "numeric_cell" or alternative in scores:
            raise ValueError("oracle needs exactly one active fixed numeric score per alternative")
        scores[alternative] = payload["value"]
    if set(scores) != {a["id"] for a in baseline["alternatives"]}:
        raise ValueError("oracle is missing a reviewed score")
    with_proxy["performances"].extend(
        {
            "alternative_id": a["id"],
            "criterion_id": state["criterion"]["id"],
            "value": scores[a["id"]],
        }
        for a in baseline["alternatives"]
    )
    return baseline, with_proxy
