"""Independent proposal selection and interchange oracle. No application imports."""

import copy
import csv
import hashlib
import io
import json


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def reviewed_cells(workspace):
    states = {e["proposal_id"]: e["review"] for e in workspace["reviews"]}
    cells = {}
    for original in workspace["intake"]["proposals"]:
        review = states.get(original["id"])
        if review is None or review["status"] == "rejected":
            continue
        payload = (
            review["corrected_payload"] if review["status"] == "corrected" else original["payload"]
        )
        if payload["kind"] == "alternative_tag":
            continue
        if payload["kind"] == "source_claim":
            payload = payload.get("measurement")
            if payload is None:
                continue
        key = (original["subject"]["alternative_id"], original["subject"]["criterion_id"])
        if key in cells:
            raise ValueError("multiple selected cell claims")
        cells[key] = payload["value"]
    return cells


def csv_payloads(text):
    rows = csv.DictReader(io.StringIO(text))
    return {
        r["proposal_id"]: {
            "payload": json.loads(r["payload_json"]),
            "source_ids": json.loads(r["source_ids_json"]),
            "tool_id": r["tool_id"],
        }
        for r in rows
    }


def compiled_cells(workspace):
    result = copy.deepcopy(workspace["source_project"])
    values = {(p["alternative_id"], p["criterion_id"]): p["value"] for p in result["performances"]}
    values.update(reviewed_cells(workspace))
    return values
