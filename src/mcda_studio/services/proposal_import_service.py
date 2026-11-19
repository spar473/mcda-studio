"""Bounded local JSON/CSV proposal interchange; no inference or partial row imports."""

import csv
import io
import json
from pathlib import Path
from typing import Any, Literal, NoReturn

from pydantic import ValidationError

from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.external_proposals import ExternalProposals, ProposalIntake
from mcda_studio.domain.project import Project
from mcda_studio.services import proposal_service as proposals

MAX_BYTES = 8_000_000
CSV_COLUMNS = (
    "schema_version",
    "project_fingerprint",
    "proposal_id",
    "proposal_version",
    "kind",
    "alternative_id",
    "criterion_id",
    "payload_json",
    "tool_id",
    "tool_version",
    "model_card_id",
    "model_card_digest",
    "run_at",
    "confidence_json",
    "source_ids_json",
    "replaces_proposal_id",
)


def _fail(message: str) -> NoReturn:
    raise ModelEditError(f"PROPOSAL_IMPORT: {message}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    _fail(f"nonfinite JSON constant {value}")


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > 32:
        _fail("JSON nesting exceeds 32 levels")
    if isinstance(value, str) and len(value) > 10_000:
        _fail("a string exceeds 10000 characters")
    if isinstance(value, dict):
        for key, item in value.items():
            _bounded(key, depth + 1)
            _bounded(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _bounded(item, depth + 1)


def strict_json(text: str) -> Any:
    if len(text.encode("utf-8")) > MAX_BYTES:
        _fail("file exceeds the 8 MB limit")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        _fail(f"invalid JSON: {exc}")
    _bounded(value)
    return value


def read_local(file: Path) -> str:
    with file.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        _fail("file exceeds the 8 MB limit")
    return raw.decode("utf-8")


def parse(
    project: Project,
    text: str,
    format: Literal["json", "csv"] = "json",
    registries_text: str | None = None,
) -> ExternalProposals:
    if len(text.encode("utf-8")) > MAX_BYTES:
        _fail("file exceeds the 8 MB limit")
    try:
        if format == "json":
            raw = strict_json(text)
            if registries_text is not None:
                _fail("JSON contains its own registries; do not supply another registry file")
            if isinstance(raw, dict) and "workspace_version" in raw:
                workspace = ExternalProposals.model_validate_json(json.dumps(raw))
                proposals.inspect(project, workspace)
                return workspace
        else:
            if registries_text is None:
                _fail("CSV requires a local registry JSON file in the same import")
            registries = strict_json(registries_text or "")
            if not isinstance(registries, dict) or set(registries) != {
                "project_fingerprint",
                "sources",
                "model_cards",
                "human_dossier",
            }:
                _fail("registry file requires fingerprint, sources, model_cards and human_dossier")
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
            header = next(reader, [])
            if tuple(header) != CSV_COLUMNS:
                _fail("CSV requires the exact published header order, without duplicates or extras")
            items: list[dict[str, Any]] = []
            for values in reader:
                line = reader.line_num
                if len(items) >= 2000:
                    _fail(f"CSV line {line}: exceeds 2000 proposals")
                if len(values) != len(CSV_COLUMNS):
                    _fail(f"CSV line {line}: wrong number of fields")
                row = dict(zip(CSV_COLUMNS, values, strict=True))
                if row["schema_version"] != "1" or row["proposal_version"] != "1":
                    _fail(f"CSV line {line}: unsupported version")
                if row["project_fingerprint"] != registries["project_fingerprint"]:
                    _fail(f"CSV line {line}: fingerprint differs from registry")
                try:
                    payload = strict_json(row["payload_json"])
                    if not isinstance(payload, dict) or payload.get("kind") != row["kind"]:
                        _fail("payload kind differs from kind column")
                    item = {
                        "id": row["proposal_id"],
                        "proposal_version": 1,
                        "subject": {
                            "alternative_id": row["alternative_id"],
                            "criterion_id": row["criterion_id"] or None,
                        },
                        "payload": payload,
                        "tool_id": row["tool_id"],
                        "tool_version": row["tool_version"],
                        "model_card_id": row["model_card_id"],
                        "model_card_digest": row["model_card_digest"],
                        "run_at": row["run_at"],
                        "confidence": strict_json(row["confidence_json"])
                        if row["confidence_json"]
                        else None,
                        "source_ids": strict_json(row["source_ids_json"]),
                        "replaces_proposal_id": row["replaces_proposal_id"] or None,
                    }
                    # Validate each row to report its physical CSV line.
                    from mcda_studio.domain.external_proposals import ExternalProposal

                    ExternalProposal.model_validate_json(json.dumps(item))
                    items.append(item)
                except (ValidationError, ModelEditError) as exc:
                    _fail(f"CSV line {line}: {exc}")
            raw = {"schema_version": 1, **registries, "proposals": items}
        intake = ProposalIntake.model_validate_json(json.dumps(raw))
        # Canonical declaration order makes JSON/CSV interchange deterministic; payloads stay exact.
        intake.proposals = sorted(intake.proposals, key=lambda p: p.id)
        result = proposals.start(project, intake)
        proposals.inspect(project, result)
        return result
    except (ValidationError, csv.Error) as exc:
        _fail(str(exc))


def csv_files(intake: ProposalIntake) -> tuple[str, str]:
    """Portable intake only; review history is exported as the workspace JSON, never as CSV."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for proposal in sorted(intake.proposals, key=lambda p: p.id):
        raw = proposal.model_dump(mode="json")
        writer.writerow(
            (
                1,
                intake.project_fingerprint,
                proposal.id,
                1,
                proposal.payload.kind,
                proposal.subject.alternative_id,
                proposal.subject.criterion_id or "",
                json.dumps(raw["payload"], ensure_ascii=False, sort_keys=True),
                proposal.tool_id,
                proposal.tool_version,
                proposal.model_card_id,
                proposal.model_card_digest,
                raw["run_at"],
                json.dumps(raw["confidence"], sort_keys=True) if proposal.confidence else "",
                json.dumps(proposal.source_ids),
                proposal.replaces_proposal_id or "",
            )
        )
    registries = intake.model_dump(mode="json", exclude={"schema_version", "proposals"})
    return stream.getvalue(), json.dumps(
        registries, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"
