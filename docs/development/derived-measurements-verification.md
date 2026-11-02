# Deterministic calculation foundation — 31 October 2026

Base: `785b1e8` (fixed-anchor measurement ranges), following the combined checkpoint `d7f8f8c`.
This is a tested deterministic foundation, not complete live project formulas or uncertainty
propagation. The [design and separate uncertainty extension](../design/derived-measurements.md)
state its boundaries; the [demonstrations](../../examples/derived_measurements/README.md) include
reproducible CLI/GUI steps and the pending fresh-user protocol.

## Implemented and reviewed

- Domain: versioned calculation models, source factors and formulas, reusing evidence source,
  origin and review records. No project-schema migration or existing numeric-method change.
- Engine: bounded arithmetic/min/max, explicit dimensions, named dependencies, memoized shared
  factors, cycle detection and coded arithmetic/reference/resource errors. No arbitrary execution.
- Service: exact-context previews with full input/provenance snapshots, immediate and fundamental
  dependencies, model/review digests, and all-or-nothing compilation into a new static project copy.
- CLI: `derived preview` and `derived compile`; exclusive output creation protects existing files.
- API/UI: `/api/derived/preview`, generated contracts, local-file preview in Measurements, formula
  and reviewed-source explanations, context checks, retry and full-precision preview download.
- Two synthetic examples use the same engine: bottom-up annual market revenue (600,000/640,000 NZD)
  and three-year supplier TCO (155,000/161,000 NZD). Both share upstream factors; TCO uses an
  intermediate formula. No VC-specific production code or external-model integration was added.

## Actual checks

| Check | Outcome |
| --- | --- |
| Final full Python suite | 1,570 passed; existing Starlette/httpx deprecation warning |
| Focused derived suite | 27 passed, including property tests and independent rational demo oracles |
| Frontend | 387 tests; TypeScript, ESLint, generated-type freshness and production build passed |
| Python static checks | Ruff, formatting and mypy (76 source files) passed |
| API schema | OpenAPI freshness passed |
| Full browser | 93 passed in 3.4 minutes; unchanged performance assertions |
| Browser after final nesting guard | Both calculation demonstrations passed again on a fresh server |
| Existing numerical/export outputs | 969/969 byte-identical to `61ff58e` |
| Existing acceptance workflows | Demo and acceptance evidence passed |
| New CLI reproduction | Preview, compile and repeated evaluation reproduced in separate processes for both examples |

Seven derived mutants were caught and the unmodified scratch baseline passed.
The range increment previously killed seven targeted mutants with its baseline
passing. Other mutation groups were not rerun in these two increments. The browser build retains
the existing large-chunk warning; no size or performance assertions were weakened.

The earlier trace-artifact failure did not recur in the 91- or 93-test full browser runs; its root
cause remains unconfirmed. A separate example-ID collision was fixed by isolating test IDs and
binding dossiers to the exact imported fingerprint.

## Remaining work, in order

1. Preserve formula trace inside project/decision snapshots and implement reviewed live formula
   editing/recalculation with project versioning and undo/redo; this slice deliberately uses local
   sidecars and static compilation. Keep original project, model and preview together.
2. Complete graphical evidence/decision-record management and the Open Questions support audit.
3. Implement and independently verify fundamental-factor uncertainty sampling and shared
   dependencies as specified separately. Existing SMAA cell distributions cannot substitute for it.
4. Conduct the independent fresh-user and accessibility checkpoints. No human acceptance is claimed.

The examples are checkout-only; release packaging was not rebuilt or retested in this increment.
No push, release, tag, external data transmission or production classifier integration occurred.
