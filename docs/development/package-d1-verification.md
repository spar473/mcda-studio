# D1 Visible model — implementation and verification

2026-10-26. Local uncommitted work on `main`, HEAD
`3c382ab5e310d8c2f1b56444772e7d523c34ee36`. Existing B, C1 and planning changes were
present before D1 and retained. No reset, clean, stash, commit, push, tag or publication.
No applicable AGENTS.md was found. This record supplements earlier verification; it does not
replace their recorded results or describe historical counts as checks executed now.

## Delivered boundary

Canvas/Outline in Model, synthetic title/goal opening existing project settings, objective and
criterion cards linked by stable IDs to the existing Inspector, explicit Edit, expand/collapse,
current setup/validation messages and immediate rendering of accepted edits and undo/redo.
Ordinary structural controls, confirmations, forms, previews and save path remain available.
Presentation state is session-only; changing view or collapse leaves project data/history intact.
No new dependency, API, schema, numerical logic, fixture or tolerance was introduced.
D2 alternatives/coverage, evidence, analytics overlays, reparenting and canvas export are excluded.

## Files and responsibilities

| Files | D1 change |
| --- | --- |
| `frontend/src/components/ModelTree.tsx` (new) | HTML cards/tree semantics, roving keyboard focus, collapse/reveal, safe fallback and decorative branch rails |
| `frontend/src/model/visibleTree.ts` (new) | Iterative indexing/traversal, structural diagnostics, visible rows and current validation issue counts |
| `TreePanel.tsx` | Shared existing toolbar/actions/confirmations, view switch, goal, successful/failed deletion focus |
| `EditorScreen.tsx` | Transient presentation state and stable existing selection/editor destinations |
| `Inspector.tsx`, `ProjectPanel.tsx` | Existing form focus/busy handling; readable deep breadcrumbs and iterative project summary |
| `frontend/src/styles.css` | Card/outline layouts, responsive wrapping, finite transitions and reduced motion |
| `frontend/tests/{model/visibleTree,components/ModelTree}.test.*` | Behavioural keyboard/selection/error checks, iterative 10,000-node defensive fixture |
| `frontend/e2e/visible-model.spec.ts` | Real-backend build/history/save, request isolation, malformed input, screenshots and repeated timings |
| `scripts/smoke_visible_model.mjs` (new), `smoke_browser.mjs`, `smoke_install.py` | Focused edit/history/save/reopen in installed wheels and pipx GUI |
| Design/roadmap/changelog/testing/handover/index | Status and limitations; B/C1 records retained |

## Checks executed

Commands ran from the repository root with `.venv` Python 3.12.15; localhost/process tests used
sandbox permission. Environment: macOS 26.5.1 arm64, Node 26.12.1, npm 11.20.0,
Google Chrome 155.0.8059.85. No other platform/browser claim is made.

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 647 passed; one existing Starlette/httpx deprecation warning; 15.41 s |
| `.venv/bin/ruff check src tests scripts hatch_build.py` | Passed |
| `.venv/bin/ruff format --check src tests scripts hatch_build.py` | Passed, 88 files |
| `.venv/bin/mypy` | Passed, 40 source files |
| `.venv/bin/python scripts/export_openapi.py --check` | Current |
| `.venv/bin/python scripts/acceptance_demo.py` | Passed save/fresh-process reopen/reproduction |
| `.venv/bin/python scripts/acceptance_evidence.py <temporary directory>` | Passed independent oracles, reconciliation, export/reopen and timings |
| `npm --prefix frontend run check` | 252 tests / 27 files, TypeScript, ESLint, generated types and production build passed |
| `MCDA_PYTHON="$PWD/.venv/bin/python" MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm --prefix frontend run test:e2e` | 72 passed (1.7 min), rerun after final visual/zoom refinements |
| `.venv/bin/python scripts/mutation_check.py` | Unmodified scratch baseline passed; 68/68 injected defects caught |
| `<temporary tools environment>/bin/python scripts/build_release.py --skip-frontend --out dist/d1` | Direct wheel, sdist and rebuilt wheel passed, including missing-GUI negative build; final hashes in `dist/d1/MANIFEST.sha256` |
| Installed browser smoke (command below) | Passed direct wheel, sdist-built wheel and pipx GUI; example evaluation/export/reopen, ownership/restore and D1 edit/history/save/reopen |
| `git diff --check` | Passed |

The mutation run copied the tree before the final decorative-rail/zoom refinements and extra
focused-keyboard test; those later frontend changes receive the full frontend/browser/install checks.
No mutation target or numerical expectation was changed by D1.

The first focused browser run passed 3/4 D1 tests; duplicate names broke a test helper which
assumed uniqueness. The test now selects by stable ID and asserts both duplicate labels; no
product workaround or relaxed numerical assertion was used. Visual review also found that CSS zoom squeezed the model pane; container-width stacking and a
usable-width browser assertion address it. Branch connector rails were refined after inspection.
The full browser suite and distribution were rerun after these changes. An earlier lint pass caught unused
imports/incorrect async usage and was corrected. No failing application/numerical checks remain
from those runs.

```sh
MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  <temporary tools environment>/bin/python scripts/smoke_install.py \
  --dist dist/d1 --browser --wheelhouse <temporary wheelhouse>
```

Build tools came from the existing package-B tooling environment, using the recorded build lock;
no dependency was added or lock changed in D1. Browser checks use temporary stores. Installed smoke
runs outside the repository with source overrides removed and checks both wheel routes plus pipx.

## Interaction, visual and accessibility observations

Automated browser interaction builds a blank model, disambiguates duplicate names, commits a
rename before Save, cancels/refuses/confirms deletion, reverses additions/renames/deletions with
history, edits the goal and saves/reopens. Presentation switches/collapse preserve stored bytes.
Selection may invoke the existing guarded criterion preview; structural navigation issues no
full evaluation, analysis record, sensitivity, edit or save request. Existing stale-success/error,
configuration, candidate, conflict, results and export suites passed unchanged.

The implementer inspected blank, small, broad, deep and long-label screenshots. Blank models show
creation controls and actual Problems; small models show goal/group/leaf hierarchy and setup text.
IDs distinguish duplicate names. Large fixtures remain vertically scrollable without pan/zoom.
At 600px the editor stacks beneath the tree; names wrap. At 200% CSS zoom controls remain reachable.
Beyond six indentation levels, actual level/parent labels and expandable breadcrumbs preserve
meaning without consuming all reading space. Reduced-motion emulation removes animation.
Continuous rails are decorative and bounded to visible indentation; no graph coordinates persist.

Keyboard checks cover arrows, Home/End, Space, Enter/edit, Delete/confirmation, collapse of a selected
descendant, external reveal and focus after deletion/undo. Flat treeitems declare level, sibling
position/count, selected/expanded state and accessible names. These are automated semantics and
interaction checks, not a screen-reader usability claim. No screen-reader or WCAG audit ran.

## Performance and evidence

Five browser runs per fixture with reduced motion. Initial display is project JSON receipt to
observed tree DOM (excludes server/network and is not a precise first-paint measure). Selection,
collapse and expansion measure root-node click to two animation frames. Timings are local observations,
not cross-platform guarantees. Raw arrays and screenshots are copied to `dist/d1/visual-evidence/`.

| Fixture | Nodes / alternatives / measurements | Initial ms | Selection ms | Collapse ms | Expand ms |
| --- | --- | --- | --- | --- | --- |
| d1-standard | 52 / 50 / 2000 | 21.6 (17.5–38.2) | 19.0 (9.9–23.9) | 27.5 (27.1–28.6) | 29.5 (27.7–30.4) |
| d1-broad | 1000 / 100 / 10000 | 143.6 (143.2–159.2) | 11.8 (9.0–28.3) | 7.9 (6.5–33.3) | 47.2 (45.4–48.9) |
| d1-deep | 1000 / 100 / 10000 | 136.6 (131.8–163.6) | 13.5 (9.9–16.8) | 7.2 (7.0–10.1) | 41.2 (38.9–43.4) |

Cells show median (min–max), five runs. Standard is the existing 52-node, three-level
performance fixture; broad has 100 root branches with bounded chains; deep has 900 objectives
in a chain and 100 leaves at level 901. All observed runs were below the provisional 1 s initial / 200 ms interaction budgets;
these observations cover root selection/collapse/expansion, not every editor or preview.
The two larger fixtures use the existing supported
1,000-node / 100-alternative / 100-leaf / 10,000-measurement envelope. The separate 10,000-node
unit fixture proves traversal safety only, not a larger supported product envelope.

Evidence (local, gitignored artifacts; not in the repository): `dist/d1/visual-evidence/` holds the
raw measurements (`d1-performance.json`) and screenshots (`d1-blank.png`, `d1-small.png`,
`d1-standard.png`, `d1-broad.png`, `d1-deep.png`, `d1-deep-long-narrow.png`, `d1-zoom.png`).

These local measurements do not justify virtualisation or a graph dependency for D1. Large
trees do require vertical scrolling; collapse and Outline are the available simplifications.


The existing Python acceptance fixture also passed; observed medians (ms): load 2.687, tree 0.028,
weights 92.365, evaluation 16.123, sweep 19.976, probe 11.136, scenarios 40.921,
result record 22.188 and CSV 194.547. These measure the existing engine path, not canvas rendering.

## Post-review fixes (2026-10-26)

An independent review of the working tree reproduced two defects; both are fixed, each with a
regression test that was run red on the unfixed code first.

- **Goal click after an uncommitted rename left focus on the goal.** The blur-started edit made
  Project title busy, and `CommitText` ignored its focus request while disabled and never retried.
  It now keeps the request until the field is enabled, and drops it if focus has moved to another
  control or the request is withdrawn. Tests: five `CommitText` focus cases in `ui.test.tsx` and a
  delayed-edit browser case in `visible-model.spec.ts`.
- **`mcda sensitivity --all -o` bypassed library ownership.** It now writes under `managed_write`
  like the other CLI result outputs. Test: `test_cli_result_outputs_respect_library_ownership`
  (`evaluate` and `sensitivity --all` into a library whose owner is held).
- **A prompt restart on the same port failed (found later, during the canvas work).** Package B's
  `startup.run_server` bound its own socket without `SO_REUSEADDR`, so connections the previous
  server had closed (TIME_WAIT) made `serve` report "Address already in use"; this caused the
  intermittent e2e web-server failures. It now sets `SO_REUSEADDR` on POSIX before binding.
  Tests: `test_a_stopped_server_restarts_on_the_same_port` (real `mcda serve` processes; failed
  with Errno 48 before the fix, then passed five consecutive runs) and
  `test_port_reuse_never_shares_a_port_with_a_live_listener`. Python suite then 651 passed; two
  back-to-back browser runs on one port both started. Included in the `dist/canvas-port-fix` build
  recorded under the canvas section below.

Re-run after the fixes on macOS arm64: 649 Python, 257 frontend and 73 browser tests passed;
Ruff, format, mypy, OpenAPI freshness and `git diff --check` clean. The mutation harness caught
68/68 (unmodified baseline passed); no mutant was added for these fixes.

The `dist/d1` artifacts predate the fixes and are retained as recorded. A new build in
`dist/review-fixes/` (`build_release.py --skip-frontend` from the freshly built frontend) produced
byte-identical direct and sdist-built wheels, SHA-256
`0f40ddf004bd0d82210d271b964fe3e7e595cd2f8034a136149083ea20f2eadc`, sdist
`263ad4cd013b74f31b823c6b7d55d98bd41cc2c5cd2bee3cdccc46b67d16ed13`. Their Python files and GUI assets
match the working tree. `smoke_install.py --dist dist/review-fixes --browser` passed outside the
checkout on both wheel routes and isolated pipx (GUI, oracle, export/reopen, ownership, restore,
D1 visible model). Artifacts are ignored local outputs, dirty-tree builds, not published. Hosted
Linux CI, a fresh-user session and a screen-reader walkthrough remain outstanding.

## Canvas value-tree diagram (2026-10-26)

At the owner's request the Canvas now follows the original study's value-tree figure, with ideas
from the landscape review; design and boundaries are in the
[canvas design](../design/live-model-canvas.md#canvas-diagram-implemented-locally-2026-10-26).
Files: `model/diagram.ts` (new), `ModelTree.tsx`, `TreePanel.tsx`, `PresentationView.tsx` (new),
`EditorScreen.tsx`, `Inspector.tsx`, `WeightsPanel.tsx`, `AlternativesPanel.tsx`,
`state/usePreviews.ts`, `styles.css`; tests `tests/model/diagram.test.ts`,
`tests/components/ModelDiagram.test.tsx` and a new browser case in `visible-model.spec.ts`.
No API, schema, dependency, numerical, fixture or tolerance change.

Checks on macOS arm64, Chrome 155: `npm --prefix frontend run check` (typecheck, lint, generated
types, 269 tests, build), full browser suite 74 passed, `pytest` 649 passed, mutation harness
68/68 with its unmodified baseline passing. One D1 browser assertion changed deliberately: at 200%
CSS zoom it required the goal card to be wider than 400 px, which fitted the old full-width card;
the diagram's goal is a fixed 160 px column, so the test now requires the goal not to be squeezed
(over 280 px at 2×) and the diagram region to stay over 400 px wide. The new browser case checks
left-to-right order against the VC example, engine weights matching `/api/weights/preview`, no
weight/evaluation/edit request from selection or collapse, every chip destination, the Inspector
keyboard route and that presentation is read-only and leaves stored bytes unchanged.

Diagram timings, five runs, same method as above (median, min–max, ms):

| Fixture | Nodes | Initial | Selection | Collapse | Expand |
| --- | --- | --- | --- | --- | --- |
| d1-standard | 52 | 42.0 (31.1–51.0) | 14.6 (2.9–30.0) | 26.7 (25.1–27.8) | 23.8 (19.7–27.3) |
| d1-broad | 1000 | 301.1 (197.9–491.9) | 15.6 (14.4–16.8) | 25.5 (18.7–30.2) | 75.7 (74.0–80.9) |
| d1-deep | 1000 | 377.6 (285.6–534.0) | 16.3 (9.7–17.7) | 27.8 (9.8–31.2) | 70.7 (66.5–72.9) |

All runs stay inside the provisional 1 s / 200 ms budgets. Initial display at 1,000 nodes is about
2–3× the list layout's (grid placement plus connector measurement); a first version also
remeasured connectors on every selection (about 33 ms), fixed by keying measurement on the visible
node IDs. The deep fixture is 900 columns wide and scrolls horizontally. Human and screen-reader
checks of the diagram remain outstanding, as for D1.

Distribution after the canvas and port-reuse changes: `build_release.py --skip-frontend --out
dist/canvas-port-fix` (frontend built after the last source change) produced byte-identical direct
and sdist-built wheels, SHA-256 `7f78082b0f6f0eeba66dbeb9392964407d4f78be8a5a7c4b4fdf9d485ef4937d`,
sdist `aa647d3fea50f6f28b833b5e7e885a025d2f6485a7447e68020afd17a4286ccc`; their Python files and GUI
assets match the working tree. `smoke_install.py --dist dist/canvas-port-fix --browser` passed outside
the checkout on both wheel routes and isolated pipx (GUI, oracle, export/reopen, ownership, restore,
visible model; the installed screenshot shows the diagram). The mutation harness then caught 68/68
with its unmodified baseline passing. Earlier `dist/d1` and `dist/review-fixes` builds are retained
unchanged. All are ignored, dirty-tree local artifacts; nothing was published.

## Acceptance and next step

Engineering checks and independent human acceptance are separate. Automated UI interaction and
implementer screenshot inspection do not satisfy the request's literal real-user finish line.
An independent person still needs to build/edit a small model, explain its hierarchy and missing
setup and confirm that editing/undo/redo feels understandable; record observations before claiming
that checkpoint passed. The broader analyst checkpoint about figures/preferences versus predictions
also remains pending. Screen-reader walkthrough and hosted Linux CI remain unverified.

Next engineering package: **D2 Connected coverage**, after review of D1 and its human checkpoint.
It has not been implemented. Unsaved draft/history recovery remains the existing session-only
limitation; malformed incoming hierarchies require source correction rather than canvas repair.
No graph library is needed for the current bounded structural view.

Final branch/HEAD remain `main` / `3c382ab5e310d8c2f1b56444772e7d523c34ee36`.
`git status --short --untracked-files=all`: 27 modified tracked files and 36 untracked files,
including all pre-existing B/C1/planning work; no staged changes (local inventory:
`dist/d1/working-tree-status.txt`). At that point all work was uncommitted; it was later committed
to `main` together with the review fixes and the canvas diagram.

Engineering acceptance passes the executed checks. The literal real-user acceptance remains
**pending**, so the full human finish line is not claimed complete. Distribution evidence (local,
gitignored): `dist/d1/MANIFEST.sha256`, `dist/d1/smoke-evidence/result.json` and the installed
visible-model record and screenshot (`0-installed-visible-model.json`, `.png`).
The direct and sdist-built wheels share SHA-256
`7584e7f6386831edad58c4466f28db8e7f7cafe2ce512751141559ae5d43e31b`.
Artifacts are ignored local outputs and have not been published.
