"""The screening report: one self-contained HTML document (``docs/design/screening-report.md``).

Every number is read from an existing Python service under an explicit profile and scenario: the
screening summary (rank, class, margin, requirements, drivers, closest change, open questions), the
method comparison (each method's leader), the evidence review (claim counts) and Open Questions.
Nothing is computed here. The document has inline CSS only: no JavaScript, external font, image or
remote asset, and it prints to A4 from a browser. It carries no wall-clock time: a date appears only
when the caller passes one, so the same inputs give the same bytes.

A section the project cannot supply (no classes, one profile, no evidence) is replaced by one plain
line. Nothing is invented to fill it.
"""

import hashlib
import html
import json
import re
from datetime import date
from typing import Any

from mcda_studio import __version__
from mcda_studio.domain.common import Severity
from mcda_studio.domain.errors import McdaError, ModelStructureError
from mcda_studio.domain.evidence import Claim, EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult
from mcda_studio.services import analysis_service, comparison_service, evidence_service
from mcda_studio.services.feasibility_service import number
from mcda_studio.services.questions_service import Question, open_questions
from mcda_studio.services.screening_summary_service import (
    ScreeningSummary,
    SummaryRow,
    screening_summary,
)

REPORT_VERSION = 2
#: Optional extra statements appended to "Read this first" (a note file or the API's ``notes``).
NOTE_MAX_LINES = 20
NOTE_MAX_CHARS = 300
#: Open questions listed per type; the totals are always stated.
QUESTIONS_PER_GROUP = 10
GROUP_TITLES = {
    "blocking": "Blocking",
    "decision_sensitive": "Could change the decision",
    "evidence_quality": "Evidence quality",
}
#: A documented convention (``docs/design/evidence-foundation.md``): a claim whose source
#: description begins with this word is a judgement claim. A dossier without it reports none.
JUDGEMENT_PREFIX = "Judgement"
#: Only statements that are true for any project. Study-specific conditions (whose information,
#: whether anyone was contacted, what the study is not) come from the project's own description,
#: which the report prints above this list, and from the optional notes.
DISCLAIMER = [
    "This report supports a screening decision. It is not advice and does not recommend any "
    "option.",
    "An overall value is a preference value under the stated weights, never a probability or a "
    "forecast.",
    "It rests on the information recorded in the project and, where supplied, its evidence "
    "dossier.",
]

CSS = """
@page { size: A4; margin: 15mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  color: #1b1b1b; background: #fff; margin: 0 auto; max-width: 190mm; padding: 8mm 0; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 18pt 0 6pt; padding-top: 6pt; border-top: 1.5pt solid #1b1b1b;
  break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; break-after: avoid; }
p, li { margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 4pt 0 8pt; }
th, td { border: 0.5pt solid #777; padding: 3pt 4pt; text-align: left; vertical-align: top; }
th { background: #eee; }
tr { break-inside: avoid; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.disclaimer { border: 1.5pt solid #1b1b1b; padding: 6pt 10pt; margin: 10pt 0; }
.disclaimer p.statement { margin: 0 0 6pt; padding-bottom: 6pt; border-bottom: 0.5pt solid #777; }
.muted { color: #444; font-size: 9pt; }
.fail { font-weight: 700; }
footer { margin-top: 18pt; border-top: 1pt solid #777; padding-top: 6pt; font-size: 8.5pt;
  color: #333; }
footer dt { font-weight: 700; float: left; clear: left; width: 38mm; }
footer dd { margin: 0 0 2pt 38mm; word-break: break-all; }
@media print { body { padding: 0; } }
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def clean_notes(notes: list[str] | None) -> list[str]:
    """The extra statements for "Read this first": at most ``NOTE_MAX_LINES`` lines of at most
    ``NOTE_MAX_CHARS`` characters, none empty. Surrounding space is trimmed; escaping is later."""
    if not notes:
        return []
    cleaned = [note.strip() for note in notes]
    if any(not note for note in cleaned):
        raise ModelStructureError("A report note cannot be empty.")
    if len(cleaned) > NOTE_MAX_LINES:
        raise ModelStructureError(f"A report takes at most {NOTE_MAX_LINES} notes.")
    if any(len(note) > NOTE_MAX_CHARS for note in cleaned):
        raise ModelStructureError(f"A report note has at most {NOTE_MAX_CHARS} characters.")
    return cleaned


def _n(value: float) -> str:
    """Prose numbers: four significant digits, no exponent, "< 0.0001" for tiny nonzero values."""
    return number(value, significant_digits=4)


def _digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    """``headers`` are (text, right-aligned); cells are already-escaped HTML."""
    head = "".join(
        f'<th class="num">{_e(h)}</th>' if num else f"<th>{_e(h)}</th>" for h, num in headers
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="num">{cell}</td>' if headers[i][1] else f"<td>{cell}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _closest_change(row: SummaryRow, names: dict[str, str], classes: dict[str, str]) -> str:
    fragility = row.fragility
    if fragility is None:
        return "not shown"
    if fragility.status == "tied":
        return "tied now with " + ", ".join(names.get(a, a) for a in fragility.tied_with)
    if fragility.status == "none":
        return "no one-way change in [0, 1]"
    assert fragility.weight_change is not None
    sign = "+" if fragility.direction == "raise" else "−"
    amount = f"{sign}{_n(fragility.weight_change)} weight on {fragility.criterion_name}"
    if fragility.kind == "rank":
        other = names.get(fragility.other_alternative_id or "", fragility.other_alternative_id)
        return f"{amount} → swaps with {other}"
    after = fragility.class_after_id or ""
    return f"{amount} → moves to {classes.get(after, after)}"


def _mandate(row: SummaryRow, requirement_names: dict[str, str]) -> str:
    status = row.requirements
    if status is None:
        return "not shown"
    if status.status == "pass":
        return "Meets all"
    ids = status.failed if status.status == "fail" else status.unknown
    label = "Fails" if status.status == "fail" else "Unknown"
    return f"{label}: " + ", ".join(requirement_names.get(i, i) for i in ids)


def _summary_table(
    project: Project, summary: ScreeningSummary, names: dict[str, str]
) -> tuple[str, list[str]]:
    available = {c.column: c for c in summary.columns}
    classes = {c.id: c.name for c in project.sorting.classes} if project.sorting else {}
    requirement_names = {r.id: r.name for r in project.requirements or []}
    notes = [
        f"{column.column.replace('_', ' ').capitalize()}: {column.reason}"
        for column in summary.columns
        if not column.available and column.reason
    ]
    headers: list[tuple[str, bool]] = [
        ("Rank", True),
        ("Alternative", False),
        ("Overall value", True),
    ]
    use_classes = available.get("classes") is not None and available["classes"].available
    use_requirements = (
        available.get("requirements") is not None and available["requirements"].available
    )
    use_fragility = available.get("fragility") is not None and available["fragility"].available
    use_questions = (
        available.get("open_questions") is not None and available["open_questions"].available
    )
    if use_classes:
        headers.append(("Class (margin)", False))
    if use_requirements:
        headers.append(("Mandate", False))
    headers.append(("Two largest contributions", False))
    if use_fragility:
        headers.append(("Closest change", False))
    if use_questions:
        headers.append(("Open questions", True))
    rows = []
    for row in summary.rows:
        cells = [_e(row.rank), _e(row.name), _e(_n(row.value))]
        if use_classes:
            margin = f" ({_n(row.margin)})" if row.margin is not None else ""
            cells.append(_e(f"{row.class_name}{margin}"))
        if use_requirements:
            text = _mandate(row, requirement_names)
            cells.append(
                f'<span class="fail">{_e(text)}</span>' if text.startswith("Fails") else _e(text)
            )
        cells.append(_e("; ".join(f"{d.name} {_n(d.contribution)}" for d in row.drivers) or "none"))
        if use_fragility:
            cells.append(_e(_closest_change(row, names, classes)))
        if use_questions:
            cells.append(_e(row.open_questions))
        rows.append(cells)
    return _table(headers, rows), notes


def _active(claim: Claim) -> bool:
    return claim.review is not None and claim.review.status != "rejected"


def _scored_cells(project: Project, configuration: AnalysisConfiguration) -> set[tuple[str, str]]:
    """Cells whose leaf carries positive weight under the configuration, with an entered value."""
    mavt = configuration.model_copy(update={"method": "mavt", "parameters": {}})
    result = analysis_service.evaluate_project(project, mavt)
    assert isinstance(result, MavtResult)
    entered = project.performance_index()
    return {
        (a.id, leaf)
        for leaf, weight in result.global_weights.items()
        if weight > 0
        for a in project.alternatives
        if (a.id, leaf) in entered
    }


def _judgement_count(
    project: Project, configuration: AnalysisConfiguration, dossier: EvidenceDossier
) -> tuple[int, int, int, int] | None:
    """(judgement-only, scored, judgement-only among qualitative or ordinal, qualitative or
    ordinal), or None if they cannot be counted. "Scored" and the second pair are in cells."""
    try:
        scored = _scored_cells(project, configuration)
    except McdaError:
        return None
    labelled = {
        node.id for node in project.criteria if node.scale is not None and not node.scale.is_numeric
    }
    by_cell: dict[tuple[str, str], list[Claim]] = {}
    for claim in dossier.claims:
        if _active(claim):
            by_cell.setdefault((claim.alternative_id, claim.criterion_id), []).append(claim)
    judged_cells = {
        cell
        for cell in scored
        if by_cell.get(cell)
        and all(c.source.description.startswith(JUDGEMENT_PREFIX) for c in by_cell[cell])
    }
    judged = len(judged_cells)
    qualitative = {cell for cell in scored if cell[1] in labelled}
    return judged, len(scored), len(judged_cells & qualitative), len(qualitative)


def _judgement_line(counts: tuple[int, int, int, int]) -> str:
    judged, scored, judged_labelled, labelled = counts
    line = f"{judged} of {scored} scored ratings rest on judgement alone"
    if labelled:
        line += f" ({judged_labelled} of {labelled} qualitative or ordinal ratings)"
    return line + "."


def _usable(project: Project, dossier: EvidenceDossier | None) -> EvidenceDossier | None:
    if dossier is None:
        return None
    review = evidence_service.preview(project, dossier)
    if any(issue.severity is Severity.ERROR for issue in review.issues):
        return None
    return dossier


def _as_of(dossier: EvidenceDossier | None) -> str:
    if dossier is None or not dossier.claims:
        return "not stated"
    reviewed = [c.review.reviewed_at.date() for c in dossier.claims if c.review is not None]
    return (max(reviewed) if reviewed else max(c.source.date for c in dossier.claims)).isoformat()


def _questions_html(questions: list[Question], names: dict[str, str]) -> str:
    out = []
    for group, title in GROUP_TITLES.items():
        members = [q for q in questions if q.group == group]
        if not members:
            continue
        shown = members[:QUESTIONS_PER_GROUP]
        out.append(f"<h3>{_e(title)} ({len(shown)} of {len(members)} shown)</h3><ol>")
        for q in shown:
            who = f" [{_e(names[q.alternative_id])}]" if q.alternative_id in names else ""
            out.append(f'<li>{_e(q.question)}{who}<br><span class="muted">{_e(q.why)}</span></li>')
        out.append("</ol>")
    return "".join(out)


def screening_report(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    dossier: EvidenceDossier | None = None,
    profile_ids: list[str] | None = None,
    generated_on: date | None = None,
    notes: list[str] | None = None,
) -> str:
    """The report for one project revision. Read-only; the same inputs give the same bytes."""
    extra = clean_notes(notes)
    requested = (configuration or project.analysis).model_copy(deep=True)
    project.resolve_scenario(requested)  # an unknown scenario is an error, never a fallback
    known = {p.id: p.name for p in project.weight_profiles}
    chosen = list(dict.fromkeys(profile_ids)) if profile_ids else list(known)
    if any(p not in known for p in chosen):
        raise ModelStructureError("A requested weight profile does not exist.")
    names = {a.id: a.name for a in project.alternatives}
    usable = _usable(project, dossier)

    readings: list[tuple[str | None, str, ScreeningSummary]]
    if chosen:
        readings = [
            (
                p,
                known[p],
                screening_summary(
                    project, requested.model_copy(update={"weight_profile_id": p}), usable
                ),
            )
            for p in chosen
        ]
    else:  # a project with no saved profile reads under its configuration
        readings = [(None, "Default weights", screening_summary(project, requested, usable))]
    primary_id, primary_name, primary = readings[0]
    primary_cfg = requested.model_copy(update={"weight_profile_id": primary_id})

    body: list[str] = [
        f"<h1>{_e(project.title)}</h1>",
        '<p class="muted">Screening report</p>',
    ]
    if project.decision_maker:
        body.append(f"<p><strong>Decision maker:</strong> {_e(project.decision_maker)}</p>")
    body.append(f"<p><strong>Evidence reviewed as of:</strong> {_e(_as_of(usable))}")
    if generated_on is not None:
        body.append(f" · <strong>Generated on:</strong> {_e(generated_on.isoformat())}")
    body.append("</p>")

    # The project's own statement (where its study-specific conditions live), then the fixed
    # statements true for any project, then the caller's notes: one box.
    judged = _judgement_count(project, primary_cfg, usable) if usable is not None else None
    lines = list(DISCLAIMER)
    if judged is not None:
        lines.append(_judgement_line(judged))
    elif usable is None:
        lines.append(
            "No evidence dossier was supplied, so the share of judgement-only ratings is not shown."
        )
    lines.extend(extra)
    statement = f'<p class="statement">{_e(project.description)}</p>' if project.description else ""
    body.append(
        f'<div class="disclaimer">{statement}<strong>Read this first</strong><ul>'
        + "".join(f"<li>{_e(line)}</li>" for line in lines)
        + "</ul></div>"
    )

    # Rankings per profile
    body.append("<h2>Screening summary by profile</h2>")
    for _id, name, summary in readings:
        body.append(f"<h3>{_e(name)}</h3>")
        if summary.status != "available":
            body.append(f"<p>{_e(summary.reason)}</p>")
            continue
        table, notes = _summary_table(project, summary, names)
        body.append(table)
        body.extend(f'<p class="muted">{_e(note)}</p>' for note in notes)
    body.append(f'<p class="muted">{_e(primary.label)}</p>')

    # Profile comparison
    body.append("<h2>Profile comparison</h2>")
    available = [(n, s) for _, n, s in readings if s.status == "available"]
    if len(readings) < 2:
        body.append("<p>The project has one weight profile, so there is nothing to compare.</p>")
    elif len(available) < 2:
        body.append("<p>Fewer than two profiles could be read, so they are not compared.</p>")
    else:
        headers = [("Alternative", False)]
        for n, s in available:
            headers.append((f"{n}: rank", True))
            if any(r.class_name for r in s.rows):
                headers.append((f"{n}: class", False))
        order = [r.alternative_id for r in available[0][1].rows]
        by = [{r.alternative_id: r for r in s.rows} for _, s in available]
        rows = []
        for alt in order:
            row = [_e(names[alt])]
            for idx, (_, s) in enumerate(available):
                reading = by[idx][alt]
                row.append(_e(reading.rank))
                if any(r.class_name for r in s.rows):
                    row.append(_e(reading.class_name or "not shown"))
            rows.append(row)
        body.append(_table(headers, rows))
        body.append(
            '<p class="muted">Each profile is a separate reading. No combined ranking is made.</p>'
        )

    # Mandate failures
    body.append("<h2>Mandate failures</h2>")
    if not project.requirements:
        body.append("<p>The project states no mandatory requirements.</p>")
    elif primary.status != "available":
        body.append("<p>The ranking is unavailable, so requirements are not shown beside it.</p>")
    else:
        requirement_names = {r.id: r.name for r in project.requirements}
        failing = [
            (r, _mandate(r, requirement_names))
            for r in primary.rows
            if r.requirements is not None and r.requirements.status != "pass"
        ]
        if not failing:
            body.append("<p>No alternative fails or leaves unknown a mandatory requirement.</p>")
        else:
            body.append("<ul>")
            body.extend(
                f"<li><strong>{_e(r.name)}</strong> (rank {_e(r.rank)} under {_e(primary_name)}): "
                f"{_e(text)}</li>"
                for r, text in failing
            )
            body.append("</ul>")
            body.append(
                '<p class="muted">A failing alternative keeps its place in every ranking; no '
                "score offsets a failure.</p>"
            )

    # Method agreement
    body.append("<h2>Method agreement</h2>")
    try:
        comparison = comparison_service.compare_methods(project, primary_cfg)
    except McdaError as exc:
        body.append(f"<p>Methods could not be compared: {_e(exc)}</p>")
    else:
        ran = [c for c in comparison.columns if c.status == "ok" and c.leaders]
        if len(ran) < 2:
            body.append("<p>Fewer than two methods ran, so their leaders are not compared.</p>")
        else:
            parts = [
                f"{c.method_label}: "
                + ", ".join(comparison.alternative_names[i] for i in c.leaders)
                for c in ran
            ]
            body.append(
                f"<p>Leader by method under {_e(primary_name)}: {_e('; '.join(parts))}.</p>"
                '<p class="muted">Each is that method’s own reading. No consensus is claimed, and '
                "methods that share inputs do not validate one another.</p>"
            )
        failed = [c.method_label for c in comparison.columns if c.status != "ok"]
        if failed:
            body.append(f'<p class="muted">Not run: {_e(", ".join(failed))}.</p>')

    # Evidence freshness
    body.append("<h2>Evidence freshness</h2>")
    if dossier is None:
        body.append("<p>No evidence dossier was supplied.</p>")
    elif usable is None:
        body.append(
            "<p>The evidence dossier does not match this project revision, so it is not used.</p>"
        )
    else:
        review = evidence_service.preview(project, usable)
        outdated = sum(1 for c in usable.claims if c.outdated)
        items = [
            f"Claims: {len(usable.claims)}",
            f"Outdated (marked outdated in the dossier): {outdated}",
            f"Disputed (cells with conflicting unrejected claims): {len(review.conflicting_cells)}",
            f"Not yet reviewed: {len(review.unreviewed_claims)}",
        ]
        if judged is not None and judged[1]:
            share = 100 * judged[0] / judged[1]
            text = (
                f"Judgement-only ratings: {judged[0]} of {judged[1]} scored ratings ({_n(share)}%)"
            )
            if judged[3]:
                labelled_share = 100 * judged[2] / judged[3]
                text += f"; {judged[2]} of {judged[3]} qualitative or ordinal ratings "
                text += f"({_n(labelled_share)}%)"
            items.append(text)
        body.append("<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>")

    # Open questions
    body.append("<h2>Top open questions</h2>")
    try:
        questions = open_questions(project, primary_cfg, usable).questions
    except McdaError as exc:
        body.append(f"<p>Open questions are unavailable: {_e(exc)}</p>")
    else:
        if not questions:
            body.append(
                "<p>No open questions were found. That does not show the decision is robust.</p>"
            )
        else:
            body.append(
                f'<p class="muted">Under {_e(primary_name)}, in the order Open Questions gives '
                "them.</p>"
            )
            body.append(_questions_html(questions, names))

    # Provenance footer
    options = {
        "profiles": [p for p, _, _ in readings],
        "scenario": primary.scenario_id,
        "evidence_supplied": dossier is not None,
        "evidence_used": usable is not None,
        "generated_on": generated_on.isoformat() if generated_on else None,
        "questions_per_type": QUESTIONS_PER_GROUP,
        "notes": len(extra),
        "report_version": REPORT_VERSION,
    }
    facts = [
        ("Project fingerprint", project.fingerprint()),
        ("Application version", __version__),
        (
            "Profiles",
            ", ".join(f"{n} ({p})" if p else n for p, n, _ in readings),
        ),
        ("Scenario", primary.scenario_id or "base"),
        (
            "Evidence dossier digest",
            _digest(usable.model_dump(mode="json")) if usable else "none loaded",
        ),
        ("Generation options", json.dumps(options, sort_keys=True)),
    ]
    body.append(
        "<footer><strong>Provenance</strong><dl>"
        + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in facts)
        + "</dl></footer>"
    )
    title = re.sub(r"\s+", " ", f"{project.title} screening report")
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{CSS}</style></head><body>\n"
        + "\n".join(body)
        + "\n</body></html>\n"
    )
