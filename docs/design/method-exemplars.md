# Method exemplars: three synthetic studies

**Status:** Accepted by the owner, 18 November 2026, in chat (every recommended decision). Direction chosen by the owner in chat on 18 November 2026
("Re-frame + exemplars"). Not built yet.

The public `mcda-studio` repository is to lead with the methods, not with venture screening. Today
the only openable studies that show the newer methods are venture studies. This note sets the
common rules for three new, invented, non-venture studies, one development each. Each study has its
own note: [clinic site selection](clinic-site-selection-example.md) (AHP),
[flood defence options](flood-defence-options-example.md) (feasibility check and PROMETHEE II) and
[engineering trade study](engineering-trade-study-example.md) (every method). The
[neutral gallery and wording](neutral-gallery-and-views.md) development comes after them.

## What exists today

Read from each example's `project.json` at `da4bd2a`, 18 November 2026:

| Example | Alternatives | Schema version | Method sections stated |
| --- | --- | --- | --- |
| `supplier_selection` | 5 | 1 | none |
| `supplier_qualification` | 5 | 2 | sorting |
| `infrastructure_procurement` | 4 | 1 | none |
| `nz_deeptech_vc` | 4 | 1 | none |
| `nz_venture_screening` | 8 | 6 | sorting, SMAA-2, PROMETHEE II, requirements |

What follows from that:

- **No shipped study states AHP at all.** The venture study states no `ahp` section.
- **SMAA-2, PROMETHEE II and the feasibility check are stated only in a venture study.** Open any
  non-venture example in the comparison view and most columns are typed "not stated" errors (the
  [comparison note](method-comparison.md) said so on 31 October; the data has not changed).
- **The engine is tested on all of these methods** with generated and supplier-derived fixtures and
  independent oracles. The gap is openable studies, not method coverage.
- **Examples are registered by hand** in three lists (`hatch_build.py`, `scripts/build_release.py`,
  `scripts/smoke_install.py`). A starter, shown in the gallery, is a separate manifest with digests.

## Goals and non-goals

**Goals:**

- Three bundled, openable studies in three different domains, so every method has a non-venture
  study that states it: AHP (new), PROMETHEE II (new), SMAA-2 (new), sorting (new, beside the
  existing supplier one) and requirements (new).
- One flagship that states every section, so the comparison view shows five real columns.
- Every number comes from the engine and is checked against an existing independent oracle.
- Existing schemas only. No change to any method's mathematics, any oracle, the 969 historical
  outputs, the twelve factor records, the client SVG fixtures or `ExportCharts.tsx`.

**Non-goals (excluded):**

- Real organisations, places, products or people, and any claim about a real system.
- Sidecars (evidence, decision record, reference cases, proposals). The studies are projects only.
- A new method, schema, route or panel.
- Treating agreement between methods as validation: they share measurements and mostly share
  structure, so agreement is not independent evidence.
- Tuning inputs to make methods agree or disagree. Each note states a design intent; the outcome
  is reported as the engine finds it, and any later change to an input is disclosed.

## Design

### 1. Shape, built from the public services API

Each study is `examples/<name>/{README.md, build.py, project.json}`.

- `build.py` uses only `mcda_studio.services`, fixes every id (project id `<name>_example`) and is
  deterministic. `python examples/<name>/build.py` rewrites `project.json`.
- A test checks that the shipped `project.json` equals what `build.py` writes.
- Alternatives are named by plain description ("Town centre site"), never by company.
- Currency is NZD, as in the supplier examples. All dates, if any, are stated as invented.

### 2. Invented, and stated as invented

Every README opens with a sentence that all names and figures are invented illustrations and not
evidence about any real system. The project description carries the same word. A test checks both.

### 3. Each method's inputs are the author's own judgement

AHP judgements, PROMETHEE weights and thresholds, SMAA-2 distributions, sorting boundaries and
swing ratings are each stated separately in `build.py` and described as judgements in the README.
None is computed from another method's output, and the README says why the weights differ between
methods (different questions, not an error to reconcile).

### 4. Registration

- The three hand-kept lists gain the study's name. A new test checks the three lists agree, so a
  fourth study cannot be added to two of them only.
- Each study's `build.py` also writes a gallery starter, `examples/starter_templates/<name>/`
  (`manifest.json` and `project.json`, schema version 1), as `nz_venture_screening/build.py` does
  for its own. Tests that count or list starters are updated and kept at least as strict.
- Docs: the examples index, `docs/README.md`, `CHANGELOG.md`, the ROADMAP row and
  `known-limitations.md` where a limit is new.

### 5. Verification, common to all three

- **A new `tests/regression/test_method_exemplars.py`** per study:
  - the shipped project equals the built one;
  - it validates cleanly for every method it states, and the methods it does not state return
    their usual typed errors;
  - for each stated method the engine equals the existing independent oracle (`sorting_oracle`,
    `promethee_oracle`, `ahp_oracle`, `feasibility_oracle`; SMAA-2 by interval containment at
    several seeds, because continuous distributions cannot be enumerated), and the comparison
    agreement is recomputed by `comparison_oracle` from each method's own result;
  - a **reviewed table of headline facts** (leaders, classes, requirement outcomes, the
    consistency flag) recorded from the oracle at build time and checked in. Without it a mutant
    that changes the data would change engine and oracle together and survive.
- **Oracles are not changed.** `testing.md` says they recompute from the project JSON. If one cannot
  take a new project as it is, I stop and ask; I do not adapt the oracle.
- **A new mutation group, `--exemplars-only`,** in `scripts/mutation_check.py`. Like the study group,
  each mutant edits the study's `build.py`, rebuilds and must make the study's test fail: an
  inclusive limit made exclusive, a threshold or boundary moved, a judgement's row and column
  swapped, a distribution kind swapped, a seed ignored, a unit changed.
- **The full gate and byte identity.** `scripts/byte_identity.py` walks a fixed list of examples,
  so a new example cannot change the 969 outputs; I run it anyway and report the hash.
- A dated record, `docs/development/<name>-verification.md`, per study.

### 6. Order

Smallest first, so each study proves a pattern the flagship reuses:

1. clinic site selection (the first shipped AHP study);
2. flood defence options (requirements and PROMETHEE II);
3. engineering trade study (every section);
4. the neutral gallery and wording development;
5. the public tree (a process, not a design: a fresh clone, sweeps, the full gate, then a stop).

Each is one development and one commit on `main`.

## Wording finding for the owner

`README.md` calls PROMETHEE II "a non-compensatory cross-check", and `ROADMAP.md` uses the same
phrase for the cross-check. The
[PROMETHEE II note](promethee-ii.md) says something narrower: a large advantage counts only up to
full preference. The [method limitations](../mathematics/method-limitations.md) say the ranking still
compensates and that a hard requirement belongs in the feasibility check. The exemplar READMEs and
the new public README use the narrower wording. Whether to correct the two lines in this tree is the
owner's call (decision 5).

## Decisions

1. **Three studies, smallest first** (clinic, flood defence, trade study). *Recommended.*
   *Alternative:* the flagship first.
2. **Each study is also a gallery starter.** *Recommended.* *Alternative:* Projects → Examples only.
3. **Projects only, no sidecars.** *Recommended.* *Alternative:* give the flagship a decision record.
4. **NZD** as in the supplier examples. *Alternative:* a neutral "money" unit.
5. **Correct the PROMETHEE II wording** in `README.md` and `ROADMAP.md`. *Recommended.*
   *Alternative:* leave this tree as it is and use the narrower wording only in the new public tree.
6. **The three domains** (vehicle concepts, flood defence, a clinic site) are proposals. Swapping a
   domain changes nothing downstream.

## Amendments

### 18 November 2026: clinic site selection implemented

The first study is built (development record, not included). What
differed from this note:

- **The three hand-kept lists did not agree already.** `scripts/build_release.py` has always omitted
  `nz_venture_screening`. The list test therefore asserts what is true and useful: every list carries
  each exemplar, the smoke list equals the wheel list (`hatch_build.py`), the release-check list sits
  inside it, and every listed example has a project and a README. The omission is recorded, not
  changed.
- **The "ordinal label's position" mutant became "an ordinal label's value moved".** A label's place
  in the scale's list changes no number, so a mutant that only moved it would be equivalent.
- **MAVT is recomputed by hand in the test.** No earlier oracle covers an invented project's MAVT
  values, so `test_method_exemplars.py` writes the additive value out in plain Python and compares
  it with the engine at 1e-12.
- **The mutation runner rebuilds each study before testing, and restores the study files after.**
  Only the pinned headline facts and the oracles can kill a mutant, not the "shipped equals built"
  check.
- **A committed frontend fixture followed the data.** `frontend/tests/fixtures/starter-catalog.json`
  is regenerated by `scripts/export_model_test_fixtures.py`; its only change is the added
  `clinic_site_selection` entry. `screening-summary.json` was not touched.
  `StarterGallery.test.tsx` now expects six starters and names the new one.

### 19 November 2026: flood defence options implemented, and a gap in the clinic development closed

The second study is built (development record, not included). What
differed from this note:

- **The comparison-view oracle is now applied to both studies.** Section 5 promised that
  `comparison_oracle` recomputes the agreement from each method's own result. The clinic development
  did not include it; this one adds it for both studies, parametrised, and it passes for each. The
  clinic record said nothing about it, which this amendment corrects.
- **The generic checks are parametrised over a `STUDIES` list** (the shipped project and starter
  equal the script's output; the project and README say they are invented), so each later study
  appends one name.
- **Ordinal labels run worst to best** in the project, as the engine requires; see the flood note.

### 19 November 2026: engineering trade study implemented

The third study is built (development record, not included). What
differed from this note:

- **SMAA-2's distributions were limited to what the existing independent sampler covers** (uniform,
  categorical and rating intervals, no shared draw), because section 5 forbids adapting an oracle. The
  study note gives the detail.
- **Class shares are checked by a sampler written in the test**, using the existing sampler's draw
  and `sorting_oracle.class_of`, because the existing sampler counts ranks only.
- **The comparison test now runs over cases** (a study and a context), six in all, so the flagship is
  compared under its saved reading, *Cost-led* and the scenario.

### 19 November 2026: decision 5 carried out

The owner accepted decision 5, so the PROMETHEE II wording is corrected in this tree: `README.md`
(two places) and `ROADMAP.md` (one) no longer call it "non-compensatory". The README now says it is a
cross-check in which a large advantage counts only up to full preference and the ranking still
compensates, and the intro and the roadmap's direction paragraph say "an outranking cross-check". The
requirement that no score can offset stays described where it belongs, as the mandate and feasibility
check. Two lines were left as they are on purpose: the roadmap's dated record of the 28 October
owner decisions ("strong criteria cannot simply offset weak ones") and its PROMETHEE II trigger text,
which are history, and which state the narrower claim the [PROMETHEE II note](promethee-ii.md) itself
makes. A search of the tests, scripts and fixtures found nothing that pins the old phrase.
