# Screening report export (share-readiness)

**Accepted by the owner through the overnight prompt, 7 November 2026** (ROADMAP row 12f,
the roadmap (not included), item 5).
Implemented as `screening_report_service`, `mcda report screening` and `POST /api/screening-report`.
It adds no stored format and changes no mathematics, project, sidecar or existing output.

## Purpose

One file a partner or co-investor can open or forward without installing anything. It reads a
project the way the Analyst view does and writes one self-contained HTML document that prints
cleanly to A4.

## The document

Inline CSS only: no JavaScript, external font, image or remote asset, and no chart (a Python-made
inline SVG is allowed but none is used). Python produces every character; the React export charts
are untouched. Every number comes from an existing service; nothing is computed in the report.

| Section | Source |
| --- | --- |
| Title, decision maker and statement, "evidence reviewed as of" | the project; the latest review date in the dossier (else the latest source date, else "not stated") |
| "Read this first" (one box): the project's own description first, then three fixed statements true for any project, the judgement count, and any caller notes | the project; fixed wording; the count below; the optional notes (see the amendment below) |
| One table per saved profile: rank, alternative, overall value, class (margin), mandate status, two largest contributions, closest change, open questions | `screening_summary_service` |
| Profile comparison: each alternative's rank and class under every profile, side by side, with no combined ranking | the same per-profile summaries |
| Mandate failures beside the ranking, with the reason | the summary's requirement status |
| One method-agreement line: each method's leader under the first profile, never a consensus; methods that could not run | `comparison_service.compare_methods` |
| Evidence freshness: claims, outdated, disputed (cells with conflicting unrejected claims), not yet reviewed, judgement-only share | `evidence_service.preview` |
| Top open questions, grouped by type, in Open Questions' own order (ten per type, with the totals) | `questions_service.open_questions` |
| Provenance footer: project fingerprint, application version, profile and scenario IDs, the dossier's SHA-256 if loaded, the generation options | the inputs |

A section the project cannot supply (no classes, no requirements, one profile, no evidence, a stale
dossier, a model the engine cannot evaluate) is replaced by one plain line and nothing is invented.
Numbers follow the display rules: no scientific notation, four significant digits in prose,
"< 0.0001" for tiny nonzero values.

**Judgement-only.** The evidence dossier has no "kind" field. By a documented convention
([evidence design note](evidence-foundation.md#judgement-claims)) a claim whose source description
begins with the word "Judgement" is a judgement claim. A scored rating is judgement-only when it has
at least one accepted claim and all its accepted claims are judgement claims. "Scored" means a leaf
with positive weight under the first profile and an entered measurement (128 of them in the venture
study, 71 of which are judgement). The count is worded as two figures: "X of Y scored ratings rest
on judgement alone (X of Z qualitative or ordinal ratings)", where Z counts the scored ratings on a
categorical or ordinal scale and the second X counts judgement-only ratings among those (the same
figure unless a numeric rating also rests on judgement). For the venture study it reads 71 of 128
and 71 of 112. A dossier that does not use the convention reports none; with no dossier the line is
replaced by one plain sentence.

**No wall-clock time.** The report has a date only when the caller gives `--generated-on
YYYY-MM-DD` (or `generated_on`), so the same inputs give the same bytes. URLs can appear only as
plain text inside question wording, never as links or loads.

## Surfaces

- CLI `mcda report screening PROJECT [--evidence FILE] [--profile ID ...] [--scenario ID]
  [--generated-on DATE] [--note-file FILE] [--out FILE]`: standard output without `--out`; a new
  file with it, never overwriting. An unknown profile or scenario is an error, never a fallback.
- `POST /api/screening-report` (project draft, configuration, optional dossier, optional profile
  IDs, date and notes), returning `text/html` as an attachment with the project fingerprint in a
  header. The OpenAPI document gained only this route and its request model (and, with the
  amendment below, the optional `notes` list).
- A **Download screening report** button in Results (Analyst and Builder views), for MAVT and
  sorting. During a what-if trial it is disabled with the existing message "Reset what-if to
  download the saved model", and a Reset or a change of revision permanently invalidates an
  in-flight request. Looking changes no project byte, fingerprint, ETag, dirty state or undo
  history.

## Limits

The report is a snapshot, not a decision record: it carries no rationale or review history. The
closest change is one-way (one weight at a time). The engine's fixed statements are true for any
project; a study's own conditions (whose information it uses, whether anyone was contacted, what
it is not) appear only because the project's description or the caller's notes say so. Opening it
in a browser and printing to A4 PDF is the supported route to a PDF; no PDF is
produced by the application.

## Verification

An independent check parses the report's table cells and compares every number with the
plain-Python screening-summary oracle and with Open Questions; a committed golden report for the
venture study is regenerated byte for byte; no script, link or remote asset; the what-if gating
(component and browser tests); API and CLI parity and refusals; and mutants (swapped rank, class
or margin; a missing disclaimer; the wrong profile; and others).

## Amendment: domain-neutral wording and optional notes

**Accepted by the owner through the follow-up prompt, 7 November 2026** (owner decision 8 of the
roadmap (not included)).

*Problem.* The first version hard-coded venture statements ("not investment advice", "public
information", "the companies were not contacted"), so a supplier or infrastructure project would
print them. Domain content belongs in data, never in engine logic.

*Change.* The report version is now 2.

1. **Fixed text.** The engine prints only three statements: "This report supports a screening
   decision. It is not advice and does not recommend any option."; "An overall value is a
   preference value under the stated weights, never a probability or a forecast."; "It rests on
   the information recorded in the project and, where supplied, its evidence dossier."
2. **The project's own description** is printed immediately above them, inside the same bordered
   "Read this first" box. The venture study's description already says it is not investment advice,
   uses public information and did not contact the companies; its `project.json` is unchanged.
3. **Optional notes.** `--note-file FILE` (UTF-8, one statement per line, blank lines skipped) and
   the API's optional `notes` list append statements to the box. At most 20 lines of at most 300
   characters each; an empty note or a longer one is refused (exit code, or HTTP 422), never cut.
   Every line is HTML-escaped. The application's button sends none, and no project, sidecar or
   other schema changes. The number of notes is recorded in the footer's generation options.
4. **The judgement count** is documented as a convention and worded as two figures (above).
5. **Goldens.** The venture golden is regenerated and a second golden, for the supplier
   qualification example (no dossier), is added, with a test that no venture phrase ("investment",
   "companies were not contacted", "startup", "public information") appears in it.

*Verification.* Mutants: the venture sentence restored to the fixed text; the project statement
left out; note lines unescaped; each limit off by one in both directions, in the service and the
API schema; the two figures swapped; numeric ratings counted as qualitative.
