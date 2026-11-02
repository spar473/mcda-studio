# Analysis retry: check record

**Date:** 27 October 2026, Pacific/Auckland. **Base:** `main` at `9325139`, uncommitted working tree.
**Scope:** analysis retry, the first of the resilience follow-ups (plan §4.2 (historical record, not included)).
Library backup and restore, OpenAPI error declarations and durable drafts remain proposed.

## What changed

- `frontend/src/state/useAnalysisRequest.ts`: the error state now carries `retry()`. It clears the
  failure (so the panel shows loading), then re-runs the request for the **same key** with a fresh
  `AbortSignal`. A retry captured under an older key does nothing. The existing key gate and
  cancellation still reject late answers. The debounce keeps repeated clicks to one request.
- Retry buttons appear under the existing error messages:
  - Results: "Retry analysis".
  - Scoped analysis check: "Retry analysis check".
  - Sensitivity: "Retry sensitivity" and "Retry probe".
  - Scenario comparison: "Retry comparison".
- Previews (Weights, value-function and canvas weights) are deliberately unchanged; they re-request
  on the next edit.
- No API, OpenAPI, schema, dependency, Python or numerical change.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15 in the project `.venv` (hash-pinned locks),
Node 26.12.1, npm 11.20.0, Google Chrome 156.0.8078.48.

| Check | Command | Result |
| --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | **651 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass |
| mypy `--strict` | `.venv/bin/mypy` | Pass (40 source files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass |
| Frontend gate | `npm --prefix frontend run check` | TypeScript, ESLint (0 warnings), type freshness, build: pass. **Vitest 278 passed** (30 files), previously 269 |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | **77 passed**, previously 74 |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | **71 of 71 killed** (68 previously, plus RT1–RT3); the unmutated copy passes |

### New tests

- `frontend/tests/state/useAnalysisRequest.test.tsx` (5 cases):
  - Retry re-sends the same request with a fresh signal and shows loading meanwhile.
  - Repeated clicks issue one request.
  - After the project changes, Retry requests the current context and never the obsolete one.
  - A Retry captured before the context changed does nothing.
  - A late answer to a retried request cannot appear under a newer context.
- Component tests (4 cases):
  - Results Retry re-sends the same project and configuration, without edits or saves.
  - Sensitivity Retry works for the sweep, then for the probe.
  - Scenario-comparison Retry never substitutes the base result.
  - The scoped analysis check is re-run before the workspace is shown.
- `frontend/e2e/analysis_retry.spec.ts` (3 cases, real backend, Chrome). Each fails exactly one
  request through `page.route`:
  - analysis record;
  - scoped analysis validation;
  - sensitivity sweep.

  Each then clicks Retry, sees the engine result, and checks that the stored project file is
  byte-identical and Undo stays disabled. The test project is the supplier-selection example.
- Mutation group `RETRY_FRONTEND` in `scripts/mutation_check.py`:
  - RT1: Retry clears the failure but never re-sends the request.
  - RT2: Retry leaves the old failure on screen while re-requesting.
  - RT3: a Retry captured under an obsolete context still acts.

  All three were killed by the full Vitest suite.

## Not verified

- **No human usability checkpoint.** No participant has used Retry or any other workflow; see the
  fresh-user checkpoint in the [roadmap](../../ROADMAP.md).
- Hosted Linux CI: not run, because nothing was pushed.
- The installed-wheel and pipx smoke routes were not re-run. Packaging is unchanged, but the bundled
  frontend assets changed.
- No screen-reader walkthrough of the new buttons.
