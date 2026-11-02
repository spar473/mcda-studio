# Showcase design: verification

2 November 2026. A presentation-only refresh of the graphical interface. No engine, API, project
file, sidecar, result or export format changed, and no test, tolerance or oracle was modified.

## What changed

- **Start page.** A short welcome line and the four starters (Blank, Supplier selection,
  Infrastructure procurement, Venture screening) as cards. Each card opens the existing starter
  gallery with that starter highlighted. A branded app bar states that the app runs locally.
- **Editor navigation.** The sections are grouped in a sidebar into four stages: Build (project,
  model, alternatives, measurements, weights, requirements and any method inputs), Analyse
  (results, sensitivity, scenarios, compare), Evidence (evidence, open questions) and Decide
  (decision record). Every section remains one click away with its original name and role.
- **Analysis bar and checks.** The resolved profile and project revision moved behind **Details**.
  The validation list became **Model checks** at the foot of the sidebar: errors open it
  automatically; warnings stay folded until shown. Issue codes and paths remain available.
- **Examples dialog.** Two example summaries are shown in reader-facing wording; the example files
  keep their original descriptions because exports embed the source project.
- **Style.** Refreshed colour tokens, spacing, cards, tables and the results toolbar, with a compact
  strip layout for narrow windows. README screenshots are in `docs/images/`.

## Gate

| Check | Result |
| --- | --- |
| Python tests | 1,957 passed |
| Ruff check and format, strict mypy, OpenAPI freshness, acceptance demo and evidence | Passed |
| Frontend unit tests, lint, typecheck and production build | 451 passed in 57 files |
| Browser tests | 113 passed |
| Mutation campaign | 344 of 344 caught (264 backend, 80 frontend); unmodified copy passes |
| Earlier numerical/export outputs | 969 of 969 byte-identical |

A follow-up review made the sidebar stages more distinct (an icon and title for each stage, its
sections on a guide line, dividers and an accent marker on the active section) and ordered the
starter cards Blank, Venture screening, Supplier selection, Infrastructure procurement, with no
"featured" badge. After it, the frontend check (451 tests, lint, typecheck, build), all 113 browser
tests and all 80 frontend mutants passed again, with the unmodified copy passing; no Python changed.

The original byte manifest kept outside the checkout was lost when the machine's temporary
directory was cleared. It was rebuilt as its verification record documents: by running the
reference commit's own `scripts/byte_identity.py` against an archive of that commit. All 969
current outputs match the rebuilt manifest. No Python source, script, test or example changed in
this development, so the captured complete factor records are unaffected; they were not re-run.

## Remaining limitations

- The visual design was reviewed in screenshots at desktop width and through the existing
  narrow-window browser tests; it has not had a separate accessibility audit.
- The results screen keeps its controls above the charts, because tests and keyboard flows rely
  on them; only their styling changed.
