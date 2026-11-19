"""Generate/check the browser component's real Python proposal contract snapshots."""

import json
import sys
from pathlib import Path

from mcda_studio.domain.external_proposals import ProposalIntake, ProposalReview
from mcda_studio.services import proposal_service as proposals
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).resolve().parents[1]


def texts():
    base = ROOT / "examples/external_proposals"
    project = JsonProjectRepository().load(base / "screening-project.json")
    intake = ProposalIntake.model_validate_json((base / "screening-intake.json").read_text())
    workspace = proposals.start(project, intake)
    events = [
        ProposalReview.model_validate_json(json.dumps(e))
        for e in json.loads((base / "screening-reviews.json").read_text())
        if e["proposal_id"] in {"readiness_b", "tag_b"}
    ]
    initial = proposals.inspect(project, workspace)
    reviewed = proposals.review(
        project, workspace, events, initial.review_digest, workspace.digest, True
    )
    compiled = proposals.compile_bundle(
        project, reviewed.workspace, reviewed.review_digest, reviewed.workspace.digest
    )
    return {
        f"proposals-{name}.json": to_json_text(value)
        for name, value in (
            ("initial", initial),
            ("comparison", proposals.inspect(project, workspace, "tool:external_b")),
            ("reviewed", reviewed),
            ("compiled", compiled),
        )
    }


if __name__ == "__main__":
    for name, text in texts().items():
        file = ROOT / "frontend/tests/fixtures" / name
        if "--check" in sys.argv:
            if file.read_text() != text:
                raise SystemExit(f"Proposal test fixture stale: {name}")
        else:
            file.write_text(text)
