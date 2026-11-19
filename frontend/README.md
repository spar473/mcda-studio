# MCDA Studio frontend

This is a React 19 + TypeScript (strict) + Vite app. It talks only to the local FastAPI server
under `/api`, and it contains **no decision mathematics**:

- what the engine accepts comes from `GET /api/meta`;
- committed changes are operations sent to `POST /api/edit`;
- results come from one completed `POST /api/analysis/record`.

Candidate input and geometry checks only add to the authoritative Python validation; they never
replace it.

## Commands

```bash
npm ci                 # exact dependency versions from package-lock.json (Node 20.19+; tested with 26.12.1)
npm run dev            # Vite dev server; proxies /api to http://127.0.0.1:8765 (MCDA_BACKEND overrides)
npm run build          # type-check, then build to dist/ (served by `mcda serve`)
npm run check          # typecheck + eslint (0 warnings) + generated-types check + unit tests + build
npm run test           # Vitest unit and component tests (jsdom)
npm run test:e2e       # Playwright against the real backend (see below)
npm run gen:types      # regenerate src/api/schema.ts from ../docs/api/openapi.json
```

`src/api/schema.ts` is **generated** from the API contract, so never edit it by hand.
`npm run check:types` fails if it is stale. When the API changes, regenerate the contract first
(`python scripts/export_openapi.py`), then the types.

## Layout

```
src/api/         client.ts (fetch + ApiError), schema.ts (generated), types.ts (aliases)
src/model/       pure functions: tree, issues, defaults, measurement operations, session reducer, value drafts
src/state/       EditorStore (serial edit queue, undo/redo, dirty state, conflicts), navigation,
                 analysis context and request hooks (records, previews, sensitivity, scenarios)
src/components/  Dashboard, EditorScreen and its panels; results/ holds charts and tables
tests/           Vitest unit and component tests
e2e/             Playwright browser tests
```

## How the screens use the API

- **Shared context.** Scenario, profile and criterion selection share one editor-owned, transient
  [analysis context](../docs/design/analysis-context.md).
- **Request safety.** Read-only requests are keyed by revision, full configuration and inputs.
  They are cancelled when obsolete and checked against the provenance of each response. Switching
  tabs or context never saves the project.
- **Weights** use `/api/weights/preview`, so judgements can be inspected before measurements are
  complete.
- **The value-function editor** opens a candidate that is never saved on its own. Plot and table
  share inputs, and curves come from `/api/value-functions/preview`. Apply is one atomic operation
  batch and one undo step; Cancel or Escape never edits. From Model it commits base functions,
  and from Scenarios it commits sparse overrides.
- **Profiles and scenarios.** `ProfileManager` and `ScenarioPanel` use immutable operations and
  replace references atomically.
- **Sensitivity.** `SensitivityPanel` draws the sweep and takes every number shown as text from
  exact backend probes.
- **Results.** `ResultsPanel` uses one completed record via `useAnalysisRecord`: linked selection
  by stable ID, SVG chart geometry, and guarded numerical downloads. Display state stays outside
  the saved project.

## End-to-end tests

`npm run test:e2e` starts `mcda serve` on a throw-away project folder (`scripts/e2e-server.mjs`,
port 8799; `MCDA_E2E_PORT` overrides it) and drives the built `dist/` in Chromium.

```bash
npx playwright install chromium        # once; or point at an existing browser:
export MCDA_CHROMIUM=/path/to/chrome   # optional
export MCDA_PYTHON=/path/to/.venv/bin/python   # Python with mcda-studio installed (do not resolve the symlink)
npm run build && npm run test:e2e
```

| Spec | Covers |
| --- | --- |
| `case-a-vc-reference.spec.ts` | The NZ deep-tech VC reference project in the GUI: structure, validation, results and weights match the report; the stored file is byte-identical after viewing |
| `case-b-new-project.spec.ts` | An unrelated three-level project built entirely in the GUI, checked against an independent TypeScript oracle and the CLI. It continues through piecewise editing, a new profile, scenarios, sensitivity, downloads and reopening in a fresh browser context |
| `editing.spec.ts` | Unsaved-change guard, validation navigation, confirmed and undoable destructive operations, duplicate/delete, and save conflicts |
| `analysis-context.spec.ts`, `previews.spec.ts` | Shared context across tabs, Base versus saved defaults, previews on incomplete models |
| `value_editor.spec.ts` | Graphical/tabular editing, atomic Apply, undo/redo, cancellation and save guards |
| `weights_profiles.spec.ts` | Hierarchy, derived weights, profile management, rapid switching and keyboard use |
| `sensitivity.spec.ts` | Sweeps, exact crossovers and read-only behaviour |
| `scenarios.spec.ts` | Overrides, duplicates, profiles, reset, undo, save and reference repair |
| `results_workspace.spec.ts` | Linked charts, heatmap, dominance, exports, CSV safety, ties and the performance fixture |
| `release_acceptance.spec.ts` | All three VC crossovers, recovery from transport failures and larger-model timings |
| `evidence-compilation.spec.ts` | Review, acknowledged compilation, both exports, import as a separate copy with its receipt, and bundle reopening in the copy and the original (venture and supplier) |
| `decision-records.spec.ts` | A decision recorded on a receipt-verified copy, exported, reopened, revised and linked, with earlier files unchanged (venture and supplier) |

Run one e2e suite at a time per disposable store. The production server (`mcda serve`) defaults to
port 8765; the e2e server is separate.
