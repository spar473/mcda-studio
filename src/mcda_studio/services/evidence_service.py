"""Reviewable compilation of accepted evidence into a separate project copy."""

import hashlib
import json
from collections import Counter, defaultdict

from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.errors import ModelStructureError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import ScaleType
from mcda_studio.domain.validation import ValidationReport, validate_structure
from mcda_studio.services import project_service as ps


class EvidenceChange(DomainModel):
    alternative_id: str
    criterion_id: str
    claim_id: str
    before: Measurement | None
    after: Measurement


class EvidenceCell(DomainModel):
    alternative_id: str
    criterion_id: str


class EvidencePreview(DomainModel):
    project_fingerprint: str
    evidence_digest: str
    review_digest: str
    changes: list[EvidenceChange]
    issues: list[Issue]
    missing_measurements: list[EvidenceCell]
    unreviewed_claims: list[str]
    outdated_claims: list[str]
    conflicting_cells: list[EvidenceCell]


def _digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def preview(project: Project, dossier: EvidenceDossier) -> EvidencePreview:
    """Validate all references and describe the exact changes without modifying either input."""
    issues = list(validate_structure(project).issues)

    def error(code: str, message: str, path: str = "") -> None:
        issues.append(Issue(severity=Severity.ERROR, code=code, message=message, path=path))

    if project.fingerprint() != dossier.project_fingerprint:
        error("EVIDENCE_STALE_PROJECT", "dossier does not match this project revision")
    counts = Counter(c.id for c in dossier.claims)
    for claim_id, count in sorted(counts.items()):
        if count > 1:
            error("DUPLICATE_CLAIM_ID", "claim id is used more than once", f"claims[{claim_id}]")
    try:
        tree = project.tree()
    except ModelStructureError:
        # The structural report already describes a malformed tree.
        tree = None
    accepted: dict[tuple[str, str], list[tuple[str, Measurement]]] = defaultdict(list)
    for claim in dossier.claims:
        path = f"claims[{claim.id}]"
        if claim.alternative_id not in project.alternative_ids():
            error("EVIDENCE_UNKNOWN_ALTERNATIVE", "unknown alternative", path)
            continue
        if tree is None or claim.criterion_id not in tree or not tree.is_leaf(claim.criterion_id):
            error("EVIDENCE_UNKNOWN_CRITERION", "criterion must be a known leaf", path)
            continue
        scale = tree.node(claim.criterion_id).scale
        if scale is None:
            error("EVIDENCE_MISSING_SCALE", "criterion has no scale", path)
            continue
        if claim.unit != scale.unit:
            error("EVIDENCE_UNIT_MISMATCH", "claim unit must match the criterion exactly", path)
            continue
        review = claim.review
        if review is None or review.status == "rejected":
            continue
        value = review.corrected_value if review.status == "corrected" else claim.value
        assert value is not None
        if scale.is_numeric:
            if isinstance(value, str) or (scale.type is ScaleType.RATIO and value < 0):
                error(
                    "EVIDENCE_INVALID_VALUE",
                    "accepted value is invalid for the numeric scale",
                    path,
                )
                continue
        elif not isinstance(value, str) or value not in scale.labels:
            error("EVIDENCE_INVALID_VALUE", "accepted value is not a scale label", path)
            continue
        accepted[(claim.alternative_id, claim.criterion_id)].append((claim.id, value))
    raw = project.performance_index()
    existing_counts = Counter((p.alternative_id, p.criterion_id) for p in project.performances)
    changes = []
    for (alt, criterion), items in sorted(accepted.items()):
        if len(items) != 1:
            error(
                "EVIDENCE_MULTIPLE_ACCEPTED",
                "only one claim may be accepted for a cell",
                f"performances[{alt},{criterion}]",
            )
            continue
        if existing_counts[(alt, criterion)] > 1:
            error(
                "EVIDENCE_DUPLICATE_MEASUREMENT",
                "resolve duplicate project measurements before compiling",
                f"performances[{alt},{criterion}]",
            )
            continue
        claim_id, value = items[0]
        changes.append(
            EvidenceChange(
                alternative_id=alt,
                criterion_id=criterion,
                claim_id=claim_id,
                before=raw.get((alt, criterion)),
                after=value,
            )
        )
    # These lists describe the proposed copy, not a claim that evidence is accurate.
    after = dict(raw)
    after.update({(c.alternative_id, c.criterion_id): c.after for c in changes})
    missing = (
        [
            EvidenceCell(alternative_id=a.id, criterion_id=leaf)
            for a in project.alternatives
            for leaf in tree.leaves()
            if (a.id, leaf) not in after
        ]
        if tree is not None
        else []
    )
    unreviewed = sorted(c.id for c in dossier.claims if c.review is None)
    outdated = sorted(c.id for c in dossier.claims if c.outdated)
    claims_by_cell: dict[tuple[str, str], set[Measurement]] = defaultdict(set)
    for claim in dossier.claims:
        if claim.review is None or claim.review.status != "rejected":
            value = (
                claim.review.corrected_value
                if claim.review is not None and claim.review.status == "corrected"
                else claim.value
            )
            if value is not None:
                claims_by_cell[(claim.alternative_id, claim.criterion_id)].add(value)
    conflicts = [
        EvidenceCell(alternative_id=alt, criterion_id=criterion)
        for (alt, criterion), values in sorted(claims_by_cell.items())
        if len(values) > 1
    ]
    evidence_digest = _digest(dossier.model_dump(mode="json"))
    review_body = {
        "project_fingerprint": project.fingerprint(),
        "evidence_digest": evidence_digest,
        "changes": [c.model_dump(mode="json") for c in changes],
        "issues": [i.model_dump(mode="json") for i in issues],
        "missing_measurements": [c.model_dump(mode="json") for c in missing],
        "unreviewed_claims": unreviewed,
        "outdated_claims": outdated,
        "conflicting_cells": [c.model_dump(mode="json") for c in conflicts],
    }
    return EvidencePreview(
        project_fingerprint=project.fingerprint(),
        evidence_digest=evidence_digest,
        review_digest=_digest(review_body),
        changes=changes,
        issues=issues,
        missing_measurements=missing,
        unreviewed_claims=unreviewed,
        outdated_claims=outdated,
        conflicting_cells=conflicts,
    )


def compile_copy(project: Project, dossier: EvidenceDossier, review_digest: str) -> Project:
    """Compile only an explicitly reviewed, still-current preview; never edit the source."""
    report = preview(project, dossier)
    if report.review_digest != review_digest:
        raise StaleRevisionError("Evidence preview changed; review it again before compiling.")
    validation = ValidationReport(issues=report.issues)
    if not validation.ok:
        raise ValidationFailed(validation)
    result = project.model_copy(deep=True)
    for change in report.changes:
        result = ps.set_performance(
            result, change.alternative_id, change.criterion_id, change.after
        )
    return result
