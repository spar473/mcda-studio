# Showcase polish: investor exploration without diagnostic noise

**Status: accepted with the owner's amendments, 6 November 2026.** Phase 0 fixes questions and fixture
portability; Phase 0b fixes range-review reminders. Their Phase 0 (development record, not included) and
Phase 0b (development record, not included) records retain
the approved D1–D4 decisions. This note specifies N1–N15, I1–I4, Analyst/Builder view,
and the clean-demo guard from the showcase brief.

Implemented before this proposal: Phase 0 is `3e371cd` (S2/S3), and Phase 0b is
`8efe702` (S1). Both have their own complete gate and passing mutation controls.
The latest gate is 2,034 Python, 466 frontend and 119 browser tests, with 369/369
mutants caught; all 969 prior outputs and twelve regenerated factor records are
byte-identical to the preceding phase. This proposal does not claim the future
interactions or clean-demo guard are implemented.

## Boundaries and recommended decisions

Python remains the sole source of values, weights, ranks, contributions, classes,
crossovers and numerical summaries. React joins IDs, renders backend ordering,
formats numbers and lays out coordinates. No project, evidence, decision, sidecar
or existing result schema changes. New stateless route envelopes below add no
stored format. Existing Python and JSON/CSV downloads retain their bytes. Client SVG exports retain the contents specified in N2 below; only React-generated ID attribute values may differ. No new memo,
release, company research, ratings, sources, public-branch work or LLM features.

The owner approved recommendations 1 (noise treatments and short caveats), 2
(early complete screening-details backend), and 4 (no drawer URL persistence).
D4 continues to retain the invented starter's stored title and artifacts.

**D5 declined:** no temporary evidence projection, dossier rebinding, or projected
copy. During a what-if trial hide the open-questions column and show exactly
“Open-question counts reflect the saved weights”. What-if re-ranks only the
Results screening summary and ranking chart. Drawer, Sensitivity and partner
comparison controls show “Reset what-if to use this”. Downloads are disabled.
“Save as new profile…” is deferred: every new interaction in this pass is
read-only and session-only.

**N2 amended:** generate the original SVG export variant on demand at download
time from the same engine record. No hidden duplicate SVG. Capture original
fixtures from `8efe702` and compare every text node, numeric attribute and
metadata field; only React-generated ID attribute values may differ. This
relaxation applies to client SVGs alone.

**Number display amended:** no scientific notation in the primary view, including
question prose. Nonzero magnitudes below 0.0001 display “< 0.0001” (with a minus
sign for negative quantities). Other values use four decimals or four significant
digits in prose, expanded to fixed notation. Stored/request precision is intact.

**Accepted rollout:** Phase 2 = N1–N15 plus details backend; 3a = I1 and I4;
3b = Analyst/Builder and clean-demo guard with its mutants; 3c = I2; 3d = slim I3;
5 = documentation. Every phase has a full gate, record and separate commit.
Extend the guard in 3c and 3d. Commit this accepted note with Phase 2. Proceed
until completion or an existing stop condition.

## Screen sketches at 1440 × 900

```text
Venture screening: NZ startups for due diligence       All changes saved   Save
Method [Value-based sorting]  Scenario [Base]  Profile [Technical/IP-led]
                                                  Analyst view | Builder view
┌──────────────────┬─────────────────────────────────────────────────────────┐
│ Results          │ Results                                                 │
│ Sensitivity      │ Screening for diligence, not a prediction of success. ⓘ │
│ Compare          │ Rank  Company      Value  Class     Mandate   Questions  │
│ Evidence         │ 1     Upstock  ↗   ...    Prioritise Meets all ...        │
│ Open Questions   │ ...                 (all numbers supplied by Python)    │
│ Decision         │ [Compare partners]                                      │
│                  │ ▸ What-if weights                                       │
│ Model complete   │ Overall values        Profile: Technical/IP-led · Base   │
└──────────────────┴─────────────────────────────────────────────────────────┘
```

The sketches show layout only. Real rendering uses engine values and existing
four-decimal display conventions.

```text
Company drawer (right, approximately 480 px; vertical scrolling)
┌───────────────────────────────────────────┐
│ Upstock                               ✕   │
│ Sector ...  Stage ...                     │
│ Rank ...  Value ...  Class ... (margin ...)│
│ Mandate: meets all / fails [plain reason]  │
│ What drives the score                     │
│ Readiness       █████████ ...             │
│ Market size     ████████  ...             │
│ ...every scored leaf, backend ordered...  │
│ Ratings and evidence                      │
│ Criterion · full rubric label             │
│ [Judgement] Source title ↗ · YYYY-MM-DD    │
│ Open questions for this company           │
│ Closest change ... [Show in Sensitivity]   │
└───────────────────────────────────────────┘
```

```text
Compare partners: [Technical/IP-led]         [Commercial/traction-led]
1 Upstock   ───────────────────────────────  1 Upstock
2 ...          ╲                     ╱      2 ...
...             ╲──────────────────╱       ...
Line colour: left profile's class. Endpoint dots: each profile's class.
Thicker lines: moves of at least two places, determined by Python.

▾ What-if weights                           What-if, not saved
Team                [────●────]  rating ...  normalised weight ...
Problem & solution  [─────●───]  rating ...  normalised weight ...
Market              [──●──────]  rating ...  normalised weight ...
Traction            [───●─────]  rating ...  normalised weight ...
                         [Reset]
```

```text
Compare (compact rank grid; values and inputs available on focus/hover/ⓘ)
Company             Mandate    MAVT   Sorting       SMAA-2   PROMETHEE II  AHP
Upstock ↗           Meets all   1     1 Prioritise   ...      ...           —
Hnry ↗              Fails ...   ...   ...           ...      ...           —
AHP is not set up for this study. [Open Pairwise]
Agreement between methods that share inputs is not independent validation. ⓘ

Evidence [All] [Disputed] [Outdated] [Judgement]
▸ Upstock
▾ Scentian Bio (a dispute is open)
  Addressable market size · [Disputed] [Accepted/Unreviewed as applicable]
  Source title ↗ · date · claim text          [Review] [Details]
```

## Shared presentation and request rules

- Add one accessible info-disclosure primitive: a real button, descriptive
  accessible name, `aria-expanded`/`aria-controls`, Escape/outside-close behaviour,
  and focus return. Closed content is absent from the accessibility tree and
  rendered text. Do not use hover alone or hide text only by colour.
- `IssueText` shows the message and “Details for this message”; code/path appear
  only when requested. Audit all 28 uses in 22 components. Several call sites are
  already inside action buttons (for example coverage navigation); split those
  into sibling action and details buttons. Never nest interactive controls.
- Keep genuine errors and incomplete-model information visible. Known missing
  setup is a neutral actionable sentence. Hnry's failed mandate stays a status
  beside its ranking; it is not an application error or a hidden alternative.
- Default display numbers use four decimals for values/weights and four
  significant digits for question prose, expanded to fixed notation. Never use scientific notation in the primary view; nonzero magnitudes below 0.0001 show “< 0.0001” (minus-prefixed for negative values); retain full precision in state and requests.
  Inputs preserve the exact untouched baseline rather than submitting their
  rounded display text. User-entered edits retain their supplied precision.
- Session keys include the source project fingerprint, complete configuration,
  resolved scenario/profile, request kind and parameters, and dossier contents
  when used. Use `useAnalysisRequest` with approximately 150 ms debounce, abort,
  stale success/error rejection and Retry. Hide old ready data immediately.
- A response must echo the requested fingerprint/configuration and resolved IDs.
  What-if envelopes distinguish source and trial record fingerprints without exposing a temporary project or dossier.
  Never relabel a stale result as the currently selected profile.
- Filter/expand/open/close/focus/probe/view operations must preserve source project
  bytes, ETag, fingerprint, saved revision, dirty state and undo/redo lengths.

### Caveats: exact short captions, full meaning retained

| Location | Proposed one-line primary caption | In the info disclosure |
| --- | --- | --- |
| Screening summary/drawer | Preference values under this profile; not probabilities or predictions. | Existing summary label, complete fragility definition and limitations |
| Study context | Screening for diligence, not a prediction of success. | Existing public-information and hypothetical-fund limits |
| SMAA-2 | Sampled acceptability under these assumptions; not a probability of success. | Full existing explanation, assumptions, sampling/exact-enumeration distinction and interval meaning |
| PROMETHEE II | Net outranking flows compare alternatives under stated preferences. | Full positive/negative/net-flow explanation and method assumptions |
| Compare | Agreement between methods that share inputs is not independent validation. | Existing complete comparison context; no averaging/consensus |
| Sensitivity | One weight at a time; other weights move proportionally. | Full one-way limitation, exact-root and tie/boundary policy |
| Open Questions | No overall importance score is calculated. | Existing coverage, heuristic and unavailable-check limitations |

For an exact-enumeration SMAA run, show an exact-enumeration caption rather than
calling it sampled; preserve the full engine explanation. Captions use semantic
notes, not warning/error styles. No export string is replaced by these captions.

## Phase 2: noise items N1–N15

| Item | UX and implementation | Expected existing assertion changes / verification |
| --- | --- | --- |
| N1 diagnostics | Shared `IssueText` disclosure, plus raw-code sites not yet using it (validation and method/provenance notes). Initial view has message only. ID/path remains copyable after opening | New `IssueText` tests for closed/open/code/path, keyboard and focus return. Update message/link tests to open details explicitly when asserting diagnostics; retain exact codes and destinations. Replace the cleanup raw-code mutant with the same fault against the new component and keep it caught |
| N2 chart captions | Primary SVG caption: title plus profile/scenario **names**. IDs, hashes, explicit/resolved provenance and full caveats go into Details. Preserve the canonical export SVG separately, as specified below | `ResultsWorkspace.test.tsx` / `results_workspace.spec.ts` assert clean visible captions and exact unchanged SVG downloads for ranking, contributions and scenario comparison under fixed browser state |
| N3 requirements | A shared React reason formatter joins `RequirementCheck.measurement` and the matching labels requirement's `allowed` array. Example: “Series B or later is outside the fund's stages (Pre-seed, Seed, Series A)”. Generic projects use the criterion/requirement names, not fund-specific assumptions. Original reason is in Details, including title/tooltips where needed | Results, Requirements, Compare and drawer tests assert the same readable failure. Python reason and feasibility JSON/CSV bytes remain unchanged; keep unknown distinct from pass/fail |
| N4 methods | Get registered methods from `/meta`, validation from existing `/analysis/validate` for each method with that method's own parameters. Disable only methods with API-confirmed missing setup; label “AHP: not set up for this study”. Preserve genuine invalid-input errors. Old state selecting absent AHP shows one neutral sentence plus Open Pairwise | Update `AnalysisControls`, Results/Sensitivity and method-view tests for disabled options and deep-state fallback. No hard-coded configured-method allowlist. Deferred/stale validation must not disable a newly configured method |
| N5 settings/order | Move SMAA-specific controls into Results → Run settings, collapsed by default. Retain `EditorStore.analysis` parameters and exact request identity. Each method result precedes feasibility; alternative-method MAVT summary stays collapsed and explicitly labelled | Run-settings tests open disclosure before changing Draws/Seed/Uncertain inputs. Existing settings requests/exports match exactly; browser checks one-row global header at 1440 px and method result before requirements |
| N6 disclaimers | Use the caption table above in `AcceptabilityView`, `FlowsView` and other long primary notes. Full engine text remains in the disclosure | Assert exact short caption and full original caveat after opening; no caveat text removed from exports or underlying result |
| N7 Compare | Default rows follow backend MAVT order; fallback to project order when MAVT cannot run. One compact rank/class cell per method, numeric quantity and method inputs/settings behind focus/hover/ⓘ. One setup sentence/action per unavailable method; other cells are plain muted dashes | Update default-order and cell-text assertions to rank/class text, while asserting the same full quantity/interval after opening. Preserve quantity names/axes and all JSON/CSV downloads. Check no horizontal main-panel overflow at 1440 px |
| N8 Sensitivity | Use the leader's backend fragility criterion; otherwise the backend-selected highest-weight eligible objective, then an eligible leaf, or no-selection explanation if none. The details route supplies this choice. Weighted criteria first; “Show unweighted criteria” reveals zero-weight entries. Baseline input shows four decimals but probes the untouched full-precision number. Revision/tolerance move to Details | Add default/fallback/singleton/zero-weight cases; update empty-start expectations to explicit backend default. Probe request equality, selected-context retention and unchanged project/history tests. Crossovers remain full precision in state |
| N9 Outranking | Compact table: criterion, direction, **PROMETHEE's own** weight, function, q, p; label codings in expandable rows. Collapse zero-weight criteria under “Unweighted (screened only)”; do not classify using MAVT weights. Inert diagnostics remain in Details. Remove preview boxes rather than derive preference curves in React | Update layout/shape expectations; retain all input/apply/undo/refusal/export assertions. Check label codings, threshold units and no auto-conversion from swing weights. Expand unweighted group before editing its rows |
| N10 Uncertainty | Replace `OUTCOME=PROBABILITY` string editing with outcome/probability rows; draft values remain strings until the existing model submission. Reuse the existing section schema, apply and undo. No normalization, probabilities, samples or distribution calculations in React | Replace syntax-error assertion with per-row field validation; retain exact assembled uncertainty JSON and malformed/duplicate/out-of-range/refused cases. One apply still creates one undo step |
| N11 Evidence | Group by company then criterion, using display names. Keep separate review state (accepted/corrected/unreviewed/rejected) and nonexclusive disputed/outdated/judgement tags. Derive disputes/outdated from backend preview lists; judgement uses the study's explicit description prefix, otherwise unclassified. All/Disputed/Outdated/Judgement filter chips. Companies collapsed except open disputes. Source link plus date; claim ID in Details | Replace flat claim-ID selectors with company/criterion/source names; assert IDs after Details. Prove all claims remain represented, multiple tags are not conflated, no reviews auto-accept, filtering/collapse preserves dossier and project bytes and history, exports unchanged |
| N12 Questions | Group by company; disputed questions, outdated, weight questions, then remaining kinds. Keep project-wide questions once in a Model-wide section. Use structured alternative/criterion IDs to label entries; code-specific presentation uses existing prose where human-readable and puts raw diagnostic/claim-ID prose in Details. Related sources join by the cell IDs, never an inferred numeric importance | Update group headings/claim-ID assertions; keep every original question represented and actionable, including blocking and unrecognized kinds. No recomputed counts or priority score. Keep exact underlying Questions response and original text in Details |
| N13 checks | With zero errors and zero notes, omit both badges and show “Model complete”. Nonzero checks remain reachable, errors open as before | Update zero-counter/text assertions in `ValidationPanel` tests; retain nonzero counts, click-to-repair and errors-open behaviour |
| N14 duplicate title | Keep stored title, generated artifacts and manifest intact. Existing invented-workflow gallery label is already distinct; optional subtitle only if needed | Assert source starter bytes and original fingerprint unchanged; do not regenerate manifests to rename it |
| N15 small text/layout | Existing full-title `title` tooltip is retained; allow graceful two-line wrapping/clamping. Qualify README repeat-build claim to the same runtime/platform, since decision metadata records environment. Update stale accepted-owner/COI statements and market/scenario domain to [0.01, 200] from the recorded build decision | Title tooltip/layout test, documentation diff, no project/starter/decision JSON regeneration. Do not infer new personal COI facts |

### N2 export preservation: original variant generated on demand

Before changing charts, capture the ranking, contributions and scenario-comparison
SVGs from `8efe702`, covering classes, Base, explicit/automatic profiles and
selected/hidden series. Commit these provenance-labelled fixtures. The export
renderer preserves the original component tree, text, numeric attributes and
metadata. At download, render that original variant from the current engine
record and presentation state, serialize it, and dispose it. Do not mount a
hidden duplicate in the application. The on-screen variant uses clean captions.

Tests compare all existing text nodes, attributes and metadata against those
fixtures. Only attribute **values** generated by React for IDs may differ; all
other attributes, including data attributes, stay exact. Pin ID generation in the
test when necessary to retain references consistently. Also compare text node
order, element structure and parsed metadata deeply. No generalized float,
whitespace, hash, provenance or text normalization. Python's 969-output gate does
not cover these SVGs and continues to require byte equality.

### New screening-details route (I1 backend, delivered early for N8)

`POST /api/screening-details`, following the existing draft summary route:

```typescript
type ScreeningDetailsRequest = {
  project: Project;
  configuration: AnalysisConfiguration;
  dossier?: EvidenceDossier;
  alternative_id?: string | null; // null: exploration metadata only
};
type ScreeningDetailsResponse = {
  project_fingerprint: string;
  configuration: AnalysisConfiguration;
  weight_profile_id: string | null; // resolved
  scenario_id: string | null;
  status: "available" | "unavailable";
  reason: string;
  sensitivity: {
    suggested_criterion_id: string | null;
    criteria: {
      criterion_id: string; name: string; parent_id: string | null;
      global_weight: number; local_weight: number;
      eligible: boolean; unweighted: boolean;
    }[]; // Python order, no client weight/rank arithmetic
  } | null;
  alternative: {
    row: ScreeningSummaryRow;
    header_facts: { criterion_id: string; label: string; measurement: number | string | null }[];
    requirements: AlternativeFeasibility | null;
    contributions: { criterion_id: string; name: string; contribution: number }[];
    ratings: {
      criterion_id: string; name: string; measurement: number | string | null;
      rubric_text: string; claim_ids: string[];
    }[];
    questions: QuestionsResult["questions"];
  } | null;
};
```

Reuse existing MAVT/sorting, feasibility, questions and summary services; no new
equations or root finding. Order all scored-leaf contributions in Python,
descending, ties in tree order, including zero contributions when global weight
is positive. Requirement criteria supply generic header facts; on this study they
include Sector, Stage and HQ. Do not hard-code venture criterion IDs in the engine
or infer sector/stage by fuzzy names. Numeric criteria without rubric labels show
their measurement/unit and optional stated rubric description, not an invented
level. No dossier means ratings still appear with a load action; no sources are
invented. Above existing limits return an honest unavailable field/column.

For N8, choose the first summary row's fragility criterion if usable; otherwise
the highest-global-weight eligible objective (tree-order tie), then an eligible
leaf. No eligible node returns null. Existing sensitivity remains able to probe
unweighted nodes once explicitly revealed. For zero-weight exclusions use the
shared Phase 0 helper, not another competing rule.

## Phase 3a: I1 company drawer

**UX.** Every rendered company name in analysis displays is a consistent trigger:
summary row/name, ranking bar, contribution segment, comparison row, partner chart,
feasibility table and company headings in Evidence/Questions. Do not hijack edit
controls or source links. On rows use one focusable company button plus Enter/
Space handling on the row; stop event propagation for nested buttons/disclosures.
Charts keep their existing linked criterion selection while also opening the
company drawer. The drawer shows the sketch sections in that order.

Header facts/rank/value/class/margin come from the details response. Label this
as MAVT screening detail when opened from another method; do not present a MAVT
rank or preference value as a PROMETHEE flow or AHP priority. Feasibility
failure uses N3's structured formatter. Evidence joins `claim_ids` to the **loaded,
verified** dossier; show full rubric text and explicit observed/judgement/proxy or
unclassified attribution. A missing dossier offers “Load the study's evidence”,
using the existing fingerprint/artifact-kind match, never a project-name match.
Lift that loader into shared session state so Evidence and the drawer use the
same dossier; loading never creates reviews or changes the project.

“Show in Sensitivity” closes the drawer, selects the returned criterion and opens
Sensitivity. No browser crossover computation. While a what-if trial is active,
drawer and Sensitivity controls show “Reset what-if to use this”.

**State/identity.** `openAlternativeId`, an optional clicked-partner profile override,
and remembered focus live beside tab state,
not inside Project/session history. A partner endpoint/name passes that endpoint's
profile to the drawer; a connecting line defaults to the left profile. Show that
profile in the drawer header, and carry it into a “Show in Sensitivity” view action
without editing the project or silently changing the global profile on open.
Use the details route with the exact active
analysis context and dossier. Changing profile/scenario/revision hides old drawer
numbers and re-requests; deleted company closes it. Do not add URL persistence.

**Keyboard.** Dialog semantics, labelled heading, close button, Escape, outside
close, real focus trap including source anchors and disclosures, inert background,
and focus return to the opener. If the opener vanished, focus the destination tab
or Results heading. Adapt the existing Modal primitive, whose current focus-query
list omits links; do not copy that omission into the drawer.

**Checks.** Python detail fields equal existing services exactly, all sixteen
study scored leaves appear, sums/ranks remain engine-owned, unsupported dossier
does not become accepted support, generic project has no invented sector/stage.
API original/draft/stored byte, fingerprint and ETag checks. Component tests for
all sections, absent dossier, keyboard/focus and stale response after switch.
Browser opens Upstock and Hnry from each trigger family and verifies the mandate
failure and full rubric/source text. Opening/closing/loading/probing leaves undo,
dirty state and project bytes unchanged.

**Mutants.** Wrong-company detail join; stale prior-profile detail shown; scoring
zero-weight mandate leaves as drivers; dropped source dates; Escape/focus-return
failure; read-only detail request accidentally editing the submitted project.

## Phase 3c: I2 partner comparison

**UX.** “Compare partners” is a session-only Results toggle. Two selectors choose
any two distinct profiles; defaults are the viewed profile and the first other
profile in project order. One-profile projects get one quiet unavailable sentence.
On the study this initially compares Technical/IP-led with Commercial/traction-led.
Backend ranks determine endpoints; the frontend only lays them out. Show tied
competition-rank labels without turning layout slots into distinct ranks. Lines
use the left profile's class colour, endpoint dots each side's class, and Python's
two-place-mover flag for thickness. Also provide a keyboard table. All names/lines
open I1. There is no average, consensus or common-profile claim. Under another
method, label this explicitly as a MAVT partner comparison, separate from that
method's own result.

**Route/shape.** `POST /api/screening-summary/profiles`:

```typescript
type PartnerRequest = {
  project: Project; configuration: AnalysisConfiguration;
  profile_ids: string[]; dossier?: EvidenceDossier;
};
type PartnerResponse = {
  project_fingerprint: string; configuration: AnalysisConfiguration;
  scenario_id: string | null;
  profiles: { profile_id: string; name: string; summary: ScreeningSummary }[];
  movements: {
    alternative_id: string; from_profile_id: string; to_profile_id: string;
    from_rank: number; to_rank: number; places_changed: number;
    emphasize: boolean; line_class_id: string | null;
  }[];
};
```

Validate distinct existing IDs; preserve requested profile order. Explicitly
override the profile in each otherwise identical configuration, so scenario
profile resolution cannot erase a requested partner. Each summary equals the
existing summary service exactly. Bound request size by existing model limits;
the UI requests two at once. Movement integers/flags are computed in Python from
those existing competition ranks, not inferred from drawing order.

**State/identity.** Key source fingerprint, complete configuration,
scenario, ordered profile IDs and dossier. Validate every nested fingerprint,
configuration and resolved profile; reject late swapped-pair/scenario successes
and failures. Selection does not change the header profile or saved project.

**Checks/mutants.** Exact per-profile oracle against the current route, scenario
with its own profile, ties, generic 2+/many/one-profile models, missing optional
classes, staleness and project immutability. Mutants: average profiles, ignore a
requested profile, use local row position as rank, compute mover flag incorrectly,
or display the old pair after selectors change. Browser toggle/open-company checks
preserve source bytes/ETag/fingerprint/history.

## Phase 3d: I3 what-if weights

**UX.** Collapsible Results panel for MAVT/value-based sorting, initially the current resolved profile's raw
ratings. Show one slider and optional numeric entry for each **baseline-positive
top-level scored objective**; no Mandate or descendants. A slider that is moved
to zero remains present until Reset; do not recalculate eligibility from the
temporary project and make it disappear. The backend returns normalized weights.
Label “What-if, not saved”; show pending status without retaining old relabelled
results. “Reset” restores source analysis without edits. Ratings are uncapped:
100 is an elicitation convention, not a validation maximum. Use `step: "any"`
when an integer slider grid would round a saved raw rating; opening or resetting
never snaps it to a different value. Display formatting never replaces that raw
value in a request. Other methods offer
a transient “Explore MAVT weights” view action rather than implying their own
flows/priorities are reweighted by swing ratings. This changes no saved default.

**Route/shape.** `POST /api/screening-summary/what-if`:

```typescript
type WhatIfRequest = {
  project: Project; configuration: AnalysisConfiguration;
  ratings: Record<string, number>; // no trial dossier or evidence projection
};
type WhatIfResponse = {
  project_fingerprint: string; // original draft
  configuration: AnalysisConfiguration; // requested context
  weight_profile_id: string | null; scenario_id: string | null;
  status: "available" | "unavailable"; reason: string;
  ratings: Record<string, number>;
  controls: {
    criterion_id: string; name: string; raw_rating: number;
    local_weight: number | null; global_share: number | null;
    slider_min: number; slider_max: number; step: number | "any";
  }[];
  trial_project_fingerprint: string | null;
  summary: ScreeningSummary | null; // no projected dossier; question column hidden
  record: ValueRecord | null; // original engine record for ranking chart only
};
```

Deep-copy the project and the resolved profile; substitute only authorized root
ratings using existing immutable edit helpers. Preserve every other judgement,
zero-weight screen, method parameter, scale, measurement and scenario override.
Never call the repository, save, editor operation history or loaded dossier's
mutators. Compute summary, chart record and controls with the existing engines.
An empty ratings map returns baseline controls/result; omitted roots retain their
source raw rating, never zero by default. Reject unknown/unscored/nested IDs and
negative/nonfinite values. An all-zero root group is a typed unavailable preview
with a plain reason, never a plausible zero ranking or an automatic normalization.

Never project or rebind evidence. No dossier is sent to the trial engine.
Hide the summary's open-question column during a trial and show exactly
“Open-question counts reflect the saved weights”. The saved dossier stays intact.

**State/request identity.** Debounce approximately 150 ms. Include source revision,
entire configuration/resolved IDs, full unrounded ratings, dossier and request
kind. Check the original fingerprint and echoed ratings, then every nested
summary/record's temporary fingerprint and configuration. New response cannot
overwrite newer slider values, Reset, profile/scenario switch, edit/undo/load or
closed panel. Cancel/reset immediately hides preview data and clears temporary
context. Retain only immutable source and temporary snapshots.

Only the Results summary and ranking chart use the trial response. Do not return
or propagate a temporary project to any other control. Drawer, Sensitivity and
partner comparison show “Reset what-if to use this” during a trial. All other
panels retain the saved context. Reset and source-context changes discard trial
results immediately without changing EditorStore, undo or storage.

During a trial, disable existing analysis/SVG download controls with the plain
instruction “Reset what-if to download the saved model”. Do not download a
temporary record under the source fingerprint or silently export different data
than the plot. Reset re-enables the unchanged original export path and bytes.

**Persistence deferred.** No “Save as new profile…” control or editing operation
is implemented in this pass.

**Oracle/checks.** For each root, generate temporary ratings and independently
create a saved-profile copy with the same complete judgements. Require exact
values, competition ranks, classes, contributions, margins and fragility between
those same-runtime engine paths. Preserve the source project's serialized bytes,
fingerprint and all sidecars. Cover alternate profile, scenario, zero slider,
all-zero group, noninteger/>100 ratings, omitted/invalid IDs, absence of any projected dossier or temporary-project propagation. Component tests use delayed transport to prove stale slider,
Reset/profile/revision successes and errors are dropped. Browser moves a slider,
sees the engine result and derived weight, resets, checks undo/ETag/file bytes,
and verifies that no save-as-profile action exists.

**Mutants.** Preview edits the original; one root rating is ignored; an omitted
root becomes zero; mandate becomes a slider; leaf ratings are lost; normalization
is performed in React; stale response overwrites a newer request/Reset; a blocked control consumes trial
context; question counts are shown during a trial.

## Phase 3a: I4 hover, focus and click consistency

Summary contribution cells, chart segments and drawer bars expose criterion,
backend contribution and rubric text on both hover and keyboard focus. Use
formatted display text while retaining the underlying full-precision number.
Company names always call the same drawer action. Clicking a sensitivity
crossover row or pressing Enter/Space moves the probe to the exact backend weight;
do not parse the rounded label. Existing crossovers already use Python roots.

No additional calculation route is needed beyond I1/I3 and the existing probe
route. Tooltip, company selection and probe state are session-only; request keys
include full-precision criterion/weight and the active saved context; trial mode blocks this action.
Tests cover keyboard and pointer parity, exact request weight, tied crossovers,
missing rubric fallback and unchanged project/history. Mutants probe the rounded
display weight, join the wrong rubric/criterion, or ignore keyboard activation.

## Phase 3b: Analyst / Builder view

Header segmented control, “Analyst view | Builder view”, session-only. Analyst
shows Results, Sensitivity, Compare, Evidence, Open Questions and Decision;
Builder shows the existing full set. Switching into Analyst while on a hidden
Build tab selects Results without an edit. Keep the loaded dossier and completed
analysis caches, but retain staleness checks; do not remount a dirty evidence
workspace and lose reviews. Project-level validation errors show “This model is
incomplete — switch to Builder view to fix it” with that action, not a hidden
problem or invented ranking.

The Venture screening **worked-example gallery action** supplies the initial
Analyst preference using its starter ID/receipt and verified fingerprint, not its
title. Other projects/fresh starters open Builder. Keep explicit mode choices in session storage keyed by project ID, with no
project field, ETag or autosave. The real study worked-example gallery action
explicitly starts Analyst even after an earlier Builder choice; ordinary opens
start Builder unless that project already has an explicit choice in this browser
session. A direct import has the same Builder default. Reload within the session
retains the explicit choice; a new browser session restores these defaults. Hidden tab navigation is reconciled; opening a fix action for
Pairwise/Requirements can switch to Builder explicitly.

Tests: every tab set, correct gallery card versus invented starter, ordinary
project/import default, mode persistence/reload scope, incomplete-model message,
retained evidence review state, focus and dirty/undo/ETag/bytes invariance. Mutants
save the mode in Project, apply Analyst to all projects, hide validation errors,
or lose dossier/review state when changing view.

## Clean-demo guard: `frontend/e2e/clean-demo.spec.ts`

Use the real e2e server and `openTab`, `readJson`, `REPO`, `waitIdle`; viewport
1440 × 900, device scale factor 1. Install console warning/error, page-error and
HTTP 4xx/5xx listeners **before** navigation and retain the URL/message on failure.
Use a clean throwaway store; no test-specific production bypass, warnings hidden
by CSS, fabricated API responses or runtime-generated fixture replacement.

Path, with an assertion checkpoint after every tab, method, filter, drawer,
profile/scenario or slider state settles:

1. Start page → real Venture screening card → Open worked example, without a
   download. Assert Analyst default. Obtain initial stored file, ETag/fingerprint
   and editor history/dirty state through established tests/UI.
2. Visit every Analyst tab; switch Builder and visit **all visible** tabs.
3. Under Commercial/traction-led and under `linear_market_size`, revisit Results,
   Sensitivity, Compare and Open Questions; also switch back to Technical/IP-led.
4. Select each API-configured method (MAVT, sorting, SMAA-2, PROMETHEE II on this
   study), visit Results, and verify AHP is labelled unavailable/disabled.
5. Restore the saved MAVT/sorting view after the method sweep and checkpoint it.
   Open and close Upstock and Hnry drawers, including keyboard focus return and
   mandate failure. In 3c extend the guard to toggle Compare partners; in 3d extend it to move a
   what-if slider, verify blocked controls/hidden question counts, and Reset.
6. Load the study evidence, filter Disputed and inspect both dispute companies.
   Return to a base state and compare source bytes, ETag, fingerprint, dirty
   state and undo/redo to the start.

At each checkpoint fail on visible `.banner.warning`, `.banner.error` or
`[role=alert]`, except an exact-caption allowlist **in the spec**. Allowlist only
the approved one-line caveat component, by stable caveat ID and full exact text;
never allow arbitrary ancestor text containing a caveat. All raw-text scans still
apply to caveats. Prefer semantic note styling so no caveat needs alert status.

Scan actually rendered text, including open popovers and details, excluding only
closed/inert/hidden disclosures and non-rendered script/style/metadata. Do not
scan DOM `textContent` indiscriminately, which includes closed details; do not
skip a whole parent containing both visible text and a closed disclosure. Use a
tested rendered-text walker and browser visibility checks. Exact prohibited
patterns from the brief:

```text
codes:         /\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/
long numbers:  /\b\d\.\d{7,}\b/
hashes:        /\b[0-9a-f]{24,}\b/
Python lists:  /\[['"][^\]]*['"]\]/
claim IDs:     /\b[a-z]+__[a-z_]+\b/
valid model:   literal "validation error(s)" is prohibited
```

The default clean path leaves diagnostic popovers closed; separate diagnostic
tests open them and assert that their full code/path exists. The clean guard
must not exempt visible diagnostic text merely because it is inside a popover.
Check the actual main panel's `scrollWidth <= clientWidth` (browser rounding at
most one pixel, not a large overflow tolerance) and visible tables at every
checkpoint. Vertical scrolling is permitted. Include a narrow-layout regression
outside this fixed-size acceptance path.

Add three guard-targeted mutants in `scripts/mutation_check.py`, each running
this exact spec through the existing real server: re-show an `IssueText` code;
restore profile/scenario range-key pollution; print a raw Open Questions float.
Require a reached **guard assertion**, not browser/server setup failure, and an
unmodified guard pass. Keep the Phase 0 question and Phase 0b range mutants too.
The spec is automatically included by the normal `test:e2e` discovery; no manual
optional command or skipped mode. Keep expensive browser mutants serial, each
with its own temporary store/port and complete process cleanup.

## Expected test/text changes and preservation checks

Before Phase 2 implementation, enumerate exact assertion names from these files
in its verification record; the permitted behaviour/text changes are only those
specified above. Existing API/oracle/numerical tests stay strict.

| Area | Existing test families expected to change | Exact reason / retained guarantees |
| --- | --- | --- |
| Diagnostics | Issue/coverage/value-function/weights/editor component tests; `measurement-coverage.spec.ts` | Code/path assertions open disclosure first; repair target, message and exact diagnostic content retained |
| Charts | `ResultsWorkspace.test.tsx`, `results_workspace.spec.ts`, sorting/chart tests | Clean visible caption and tooltip; original SVG export contents, numeric metadata, class bands, selected/hidden series retained |
| Method controls/settings | `AnalysisControls`, method-view, SMAA/Results/Sensitivity tests; `smaa.spec.ts`, `method_comparison.spec.ts` | Unconfigured option disabled, neutral fallback, settings opened in Results; configuration and complete exports unchanged |
| Compare | Compare component/browser tests, proxy advanced-panel tests | Backend MAVT order and compact rank grid replace project order/full inline values; all numeric quantities and caveats still inspectable; CSV/JSON untouched |
| Sensitivity | Component/state tests and `sensitivity.spec.ts`, `screening-summary.spec.ts` | Python-selected default instead of empty choice, unweighted disclosure and rounded display input; full-precision requests, ties/roots and read-only properties retained |
| Outranking/Uncertainty | Component tests, `promethee.spec.ts`, `smaa.spec.ts` | Table/expandable coding/outcome rows replace long fieldsets/text syntax/shape boxes; apply/undo/validation and method parameters retained |
| Evidence/Questions | Evidence/Questions components, `evidence-workspace.spec.ts`, `venture-screening-study.spec.ts`, `open-questions.spec.ts` | Company/criterion/source selectors replace primary raw IDs; IDs remain in Details, no questions/claims silently dropped, filters read-only |
| Model checks/title | Validation/editor tests, relevant build workflows | Zero badges disappear and complete text shortens; nonzero errors/navigation remain; full title tooltip/text preserved |
| New interactions/view | New detail/partner/what-if/view tests and clean-demo spec | New functionality, not weakened earlier acceptance; all interactions proven read-only; profile persistence deferred |

The shared full caveats remain available verbatim in disclosures. API messages,
feasibility reasons, stored title, JSON/CSV bodies and historical fixtures do not
change for presentation polish. D2's six-path float exception remains confined
to the single screening-summary component snapshot; do not expand it to new
fields or tests without review.

## Gates, records and rollout

Phase 2: N1–N15 and complete details backend. Phase 3a: drawer and I4.
Phase 3b: Analyst/Builder and clean-demo guard/mutants. Phase 3c: partner comparison
and guard extension. Phase 3d: slim read-only what-if and guard extension.
Phase 5: walkthrough, README images at device scale factor 2, handover, roadmap,
limitations and changelog. Every phase has its own full gate, mutations, record
and commit. No release/push. Verification records and 1440 × 900 scale-factor-1
before/after images go under `docs/development/` and `images/showcase/`.
Run heavy checks serially.

Before every implementation commit: full pytest, Ruff check/format, mypy,
OpenAPI freshness, acceptance demo/evidence, frontend check, complete Playwright
and complete mutation campaign with passing unmodified control. Regenerate
OpenAPI/types when routes/models change. Compare all 969 outputs and complete
factor records against the phase's prior commit, and client SVGs against their
fixtures captured from `8efe702`, with only the approved React ID-value exception. Do not silently refresh numerical fixtures to pass.

## Risks and review stops

- Client SVG content preservation needs explicit fixtures: on-demand rendering
  must retain all original text, geometry and metadata; React ID values alone
  may differ. A substantive mismatch is a stop condition.
- Details aggregation and live what-if summary compute exact crossovers; 150 ms
  debounce is not a performance guarantee. Retain limits/cancellation, benchmark
  the real study and larger generic fixtures, and show pending state honestly.
- A profile or scenario switch, model edit, dossier review, Reset or out-of-order
  transport can combine incompatible context. Test successes **and errors**;
  never use a source fingerprint for a temporary result.
- Evidence is never projected. During trials hide the question column and block
  drawer, Sensitivity and partner comparison with the accepted reset instruction.
- Grouping by company must retain model-wide and unrecognized questions, multiple
  claims per cell, overlapping dispute/outdated/judgement tags and rejected claims
  where the existing workspace lets them be inspected.
- Drawer/modal/popover focus traps must include anchors, hidden/disabled controls
  and fallback focus when their opener disappears. Keyboard tests are necessary;
  screen-reader/WCAG acceptance and Safari remain separate unverified work.
- Linux evidence currently covers the pre-fix failure reported by the owner, not this
  proposed work. Report actual hosted/Linux runs separately; never call a workflow
  file or simulated platform label a Linux verification.
- Stop before any existing schema/mathematics/export change, caveat deletion,
  accepted-design deviation, unweakened-oracle failure or non-read-only interaction.
  Batch specific evidence and proposed choices for the owner; no push/tag/public work.


## Accepted design amendments requested with Phase 1 review

The following are changes to accepted presentation contracts, not test cleanup:

- `docs/design/method-comparison.md` §GUI currently promises project-order rows,
  header inputs/parameters and primary method quantities/axes. N7 changes the
  default to MAVT order and moves full quantities, each method's **own** axis and
  configuration into its disclosure. Values are not dropped or combined; the
  non-independent-agreement caveat stays primary. Amend that note before changing
  the corresponding assertions.
- `docs/design/results-and-exports.md` currently offers full-precision on-screen
  inspection and criterion IDs in the contribution legend. Keep raw inspection
  in Details and IDs in legend Details; primary labels stay rounded. A full-
  precision setting continues to affect the legacy export/presentation snapshot,
  while the clean renderer uses rounded labels. This preserves old export bodies
  and exact raw inspection without putting long decimals back in the primary view.
- `docs/design/method-seam.md` §frontend dispatch currently locates method settings
  in the header. N4/N5 change availability presentation and settings location,
  while retaining transient method/parameter selection and explicit saved-default
  edits. Missing setup is not an evaluated zero result.
- The Outranking editor's accepted illustrative function shapes are removed under
  N9. Retain q/p/unit semantics and backend validation; do not weaken those tests
  when replacing the shape-presence assertion with the compact table contract.
- The current sidebar and flat Evidence/Questions presentation are replaced by
  N11–N13's grouping and quiet complete state. Preserve every record, repair link,
  blocking question, review confirmation and exact exported history. The study's
  existing explicit observed/judgement/proxy prefix is a display convention, not
  a new schema or automatically inferred evidence quality score.

Known existing tests whose selectors, location or visible text must change (all
numeric/source assertions stay unless an explicitly listed presentation change
requires moving their inspection into Details):

| File | Exact existing test title(s) / planned change |
| --- | --- |
| `frontend/tests/components/AnalysisControls.test.tsx` | “lists every registered method by label and marks the saved default”; “choosing a method is a view: it selects, and never writes the saved default” — add API-derived unavailable-option state while retaining registered labels and no-edit assertions |
| `frontend/tests/components/ComparePanel.test.tsx` | “shows one column per method, naming its method, inputs, parameters and own label”; “shows each method's own numbers, a failed method's typed error, and opens the tab that fixes it”; “draws each quantity on its own axis, never a shared one”; “orders rows by one column's own rank and downloads the comparison” — compact default row/cell text, open disclosures before exact full-value/axis/code assertions, keep exports and editor destinations |
| `frontend/tests/results/ResultsWorkspace.test.tsx` | “renders competition ranks, all contribution segments and mixed-unit partial values by stable ID”; “selecting heatmap and chart elements links alternative, criterion and hierarchy without reevaluation or edits”; “sort and full precision are presentation state, and preserve competition rank/IDs”; “SVG downloads include revision, common axis and explicit hidden-series metadata with no scripts” — add drawer activation and clean caption/raw-details checks; preserve linked IDs, no-edit/no-reevaluation and exact export data, verify SVG contents against `8efe702` fixtures with the approved ID-value exception |
| `frontend/tests/results/Acceptability.test.tsx` | “shows only the Acceptability view, under its label”; “appear only for a method with acceptability, and change the view, not the project” — assert the short/full caveat split and interact with settings inside Results rather than the global header; keep full estimates, intervals, settings payloads and panel dispatch |
| `frontend/tests/components/SensitivityPanel.test.tsx` | “labels the resolved context and the axes without needing hover”; “asks the engine for an arbitrary weight instead of interpolating the grid”; “refuses to plot a criterion the engine cannot vary, and says why” — provenance moves to Details, exact probes remain, the default/revealed-unweighted states use backend metadata; all stale/probe/error invariants remain |
| `frontend/tests/components/SortingSensitivity.test.tsx` | “lists first class changes, probes their exact weight and shows classes at the probed weight” — crossover row activation and rounded display only; keep exact submitted weight/class data |
| `frontend/tests/components/OutrankingPanel.test.tsx` | “states every leaf's direction, weight, function and codes, applied as one edit”; “draws each function's shape from its thresholds alone”; “shows the engine's issues for the saved section, checked under PROMETHEE II” — table/coding disclosure replaces fieldset/shape; exact inputs, thresholds, own-method validation and one edit retained |
| `frontend/tests/components/UncertaintyPanel.test.tsx` | “states distributions, a shared draw and weight intervals, applied as one edit”; “offers only a categorical distribution for a labelled scale”; “refuses an entry that is not a number and applies nothing”; “loads the saved section, removes it only after confirmation, and shows only its own issues” — outcome row selectors/error text and issue disclosure; same section JSON, refusal, delete confirmation and one edit |
| `frontend/tests/components/EvidenceWorkspacePanel.test.tsx` | “stays read-only until a file is selected and explains provenance, support and affected measurements”; “previews a backend review and requires explicit confirmation before changing the workspace”; “offers the study's own evidence in one action when the project is exactly its worked example” — grouped claim/source selectors, retained review/load/fingerprint semantics; every other stale/refusal/binding assertion remains |
| `frontend/tests/components/QuestionsPanel.test.tsx` | “shows actionable grouped questions and limitations without editing the project”; “keeps the SMAA heuristic label and routes new signals to their editors”; “explains range witnesses separately from boundary contacts” — company/type presentation and short/full explanations; keep exact heuristic, destination and witness/contact distinction |
| `frontend/tests/components/CoverageMatrix.test.tsx` | “labels presence, attention and setup in text and exposes the engine issue as a link” — the issue button is found by its message, code asserted after the adjacent Details action. Keep the exact OUT_OF_DOMAIN code and repair target; avoid nested buttons |
| `frontend/tests/components/ProfileManager.test.tsx` | “switching is view state and does not change the saved default or project” — stable ID prose moves into Details; keep exact selected profile, saved default and non-mutating assertions |
| Model checks | Add `frontend/tests/components/ValidationPanel.test.tsx` for zero badges/“Model complete” and nonzero repair links. No existing dedicated zero-counter unit assertion was found; retain `case-a-vc-reference.spec.ts`'s real local-anchor warning checks |
| Browser suites | Update affected exact visible-text/location selectors in `results_workspace.spec.ts`, `smaa.spec.ts`, `promethee.spec.ts`, `method_comparison.spec.ts`, `measurement-coverage.spec.ts`, `evidence-workspace.spec.ts`, `venture-screening-study.spec.ts`, `open-questions.spec.ts` and `screening-summary.spec.ts`; expand relevant disclosures first. Existing backend comparisons, SVG/JSON/CSV contents, stable IDs, saved-file and undo checks stay |

Any additional assertion change discovered during implementation must be recorded
by exact name and reason in that phase's record. If it encodes an accepted rule
outside these amendments, stop for review rather than broadening approval.

**Accepted:** The owner approved the note with the amendments recorded above on
6 November 2026. D5 declined, I3 slimmed, N2 replaced, number display amended,
and rollout reordered. No further approval is required within this scope.
