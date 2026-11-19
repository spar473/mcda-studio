# Changelog

## 0.1.0 (unreleased), 19 November 2026

The first public tree of the method-focused MCDA Studio: a curated, single-commit snapshot of a private
working repository, whose dated development records are not included.

- **Methods:** additive MAVT with hierarchical swing weighting; value-based sorting into ordered classes;
  SMAA-2 acceptabilities under stated uncertainty; PROMETHEE II outranking flows with an explanation
  against MAVT; AHP priorities with consistency checks; a feasibility check of mandatory requirements;
  and a comparison view that shows each method's own reading with no consensus score.
- **Worked examples (invented):** an engineering trade study that states every method, flood defence
  options (a requirement beside every ranking, and PROMETHEE II), clinic site selection (AHP), and the
  supplier and infrastructure examples; each is checked against independent oracles with a table of
  headline facts pinned in the tests.
- **Application:** a local FastAPI service and a React/TypeScript interface, with an Analyst view and a
  Builder view, scenarios, exact one-way sensitivity, evidence review, decision records and a
  self-contained screening report. The interface only draws results the Python engine computes.
- **Reproducibility:** all 969 historical numerical and export outputs are byte-identical on macOS and
  Linux; the engine uses portable arithmetic so the same bytes come out on each platform.
- **Not in this tree:** the development records, the roadmap and the agent instructions of the working
  repository. Links to them in the design notes read "development record, not included".
