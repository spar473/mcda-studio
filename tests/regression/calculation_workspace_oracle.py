"""Independent replay of a calculation workspace's definitions and reviews; no application imports.

Applications and rebinds change the bound project, not the model's factors or formulas, so this
replay ignores them; the regression test checks the applied project separately."""

import copy


def replay(workspace: dict) -> dict:
    model = copy.deepcopy(workspace["original_model"])
    for event in workspace["events"]:
        kind = event["kind"]
        if kind == "unit":
            model["units"][event["unit"]] = event["dimension"]
        elif kind in ("source", "formula"):
            key, entry = (
                ("sources", event["factor"]) if kind == "source" else ("formulas", event["formula"])
            )
            ids = [item["id"] for item in model[key]]
            if entry["id"] in ids:
                model[key][ids.index(entry["id"])] = copy.deepcopy(entry)
            else:
                model[key].append(copy.deepcopy(entry))
        elif kind == "review":
            key = "sources" if event["entry"] == "source" else "formulas"
            (item,) = [item for item in model[key] if item["id"] == event["id"]]
            item["review"] = copy.deepcopy(event["review"])
        elif kind == "remove":
            key = "sources" if event["entry"] == "source" else "formulas"
            model[key] = [item for item in model[key] if item["id"] != event["id"]]
        else:
            assert kind in ("apply", "rebind")
    return model
