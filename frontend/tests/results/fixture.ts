import type { AhpAnalysisRecord, AnalysisRecord, PrometheeAnalysisRecord, Project, SmaaAnalysisRecord, SortingAnalysisRecord } from "../../src/api/types";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith, ratioScale } from "../fixtures";

const vf = { kind: "linear" as const, direction: "increasing" as const, out_of_domain: "error" as const };
export const project: Project = projectWith([
  node("g", null, 0),
  node("cost", "g", 0, { name: "Cost", description: "A long criterion description for the selected performance range", scale: ratioScale, value_function: vf }),
  node("quality", "g", 1, { name: "Quality", scale: { ...ratioScale, unit: "%" }, value_function: vf }),
], { alternatives: [{ id: "c", name: "An unusually long alternative name for rendering and overflow checks", metadata: {} }, { id: "a", name: "Same", metadata: {} }, { id: "b", name: "Same", metadata: {} }],
  analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
  weight_profiles: [{ id: "first", name: "First profile", method: "swing", judgements: { cost: 100, quality: 100 } }, { id: "second", name: "Second profile", method: "swing", judgements: { cost: 100, quality: 100 } }],
});
export const context = resolveContext(project, "fp", BASE_SELECTION);
export const record: AnalysisRecord = {
  record_version: "1", record_digest: "a".repeat(64), project_title: "P", scenario_name: "Base model", resolved_profile_name: "First profile",
  calculation_path: "mavt.math_fsum.v1", comparison_calculation_path: "mavt.math_fsum.v1", numerical_tolerance: 1e-12, csv_text_policy: "text-prefix-controls-v1",
  alternative_order: ["c", "a", "b"],
  criteria: [
    { criterion_id: "cost", name: "Cost", description: "A long criterion description for the selected performance range", path_ids: ["g", "cost"], path_names: ["G", "Cost"], scale: ratioScale, value_function: vf, function_source: "base", resolved_domain: { lower: 0, upper: 10, source: "fixed" } },
    { criterion_id: "quality", name: "Quality", description: "", path_ids: ["g", "quality"], path_names: ["G", "Quality"], scale: { ...ratioScale, unit: "%" }, value_function: vf, function_source: "base", resolved_domain: { lower: 0, upper: 10, source: "fixed" } },
  ], path_shares: { g: 1, cost: .5, quality: .5 }, contribution_totals: { a: .7, b: .7, c: .2 }, dominance_enabled: true,
  dominance_relations: { a: { a: "same_alternative", b: "incomparable", c: "dominates" }, b: { a: "incomparable", b: "same_alternative", c: "dominates" }, c: { a: "dominated_by", b: "dominated_by", c: "same_alternative" } },
  result: { method: "mavt", schema_version: 1, project_id: "p1", project_fingerprint: "fp", configuration: context.configuration, weight_profile_id: "first", scenario_id: null,
    ranking: [{ alternative_id: "a", name: "Same", rank: 1, value: .7 }, { alternative_id: "b", name: "Same", rank: 1, value: .7 }, { alternative_id: "c", name: project.alternatives[0]?.name ?? "C", rank: 3, value: .2 }],
    leaf_order: ["cost", "quality"], local_weights: { g: 1, cost: .5, quality: .5 }, global_weights: { cost: .5, quality: .5 }, resolved_domains: { cost: { lower: 0, upper: 10, source: "fixed" }, quality: { lower: 0, upper: 10, source: "fixed" } }, weight_basis: "Swing over the stated ranges", assumptions: ["Compensatory MAVT"], diagnostics: [],
    alternatives: [
      { alternative_id: "a", name: "Same", rank: 1, overall_value: .7, raw_measurements: { cost: 8, quality: 6 }, partial_values: { cost: .8, quality: .6 }, weighted_contributions: { cost: .4, quality: .3 }, clamped_criteria: [] },
      { alternative_id: "b", name: "Same", rank: 1, overall_value: .7, raw_measurements: { cost: 6, quality: 8 }, partial_values: { cost: .6, quality: .8 }, weighted_contributions: { cost: .3, quality: .4 }, clamped_criteria: [] },
      { alternative_id: "c", name: project.alternatives[0]?.name ?? "C", rank: 3, overall_value: .2, raw_measurements: { cost: 2, quality: 2 }, partial_values: { cost: .2, quality: .2 }, weighted_contributions: { cost: .1, quality: .1 }, clamped_criteria: [] },
    ], dominance: [{ dominator_id: "a", dominated_id: "c" }, { dominator_id: "b", dominated_id: "c" }],
  }, comparison: null, comparison_diagnostics: [],
};

/** The same model viewed as value-based sorting: classes Go (from 0.5) and Stop. */
export const sortingContext = resolveContext(project, "fp", { ...BASE_SELECTION, method: "mavt_sorting" });
export const sortingRecord: SortingAnalysisRecord = {
  record_version: "2", record_digest: "b".repeat(64), method: "mavt_sorting", method_label: "Value-based sorting (MAVT)",
  calculation_path: "mavt_sorting.math_fsum.v1", comparison_calculation_path: "mavt.math_fsum.v1", numerical_tolerance: 1e-12,
  csv_text_policy: "text-prefix-controls-v1", project_title: "P", scenario_name: "Base model", resolved_profile_name: "First profile",
  alternative_order: record.alternative_order, configuration: sortingContext.configuration,
  criteria: record.criteria, path_shares: record.path_shares, contribution_totals: record.contribution_totals,
  dominance_enabled: record.dominance_enabled, dominance_relations: record.dominance_relations,
  result: { ...record.result, method: "mavt_sorting", configuration: sortingContext.configuration, boundary_tolerance: 1e-12,
    classes: [
      { class_id: "go", name: "Go", rank: 1, lower_boundary: 0.5, upper_boundary: null, alternative_ids: ["a", "b"] },
      { class_id: "stop", name: "Stop", rank: 2, lower_boundary: null, upper_boundary: 0.5, alternative_ids: ["c"] },
    ],
    assignments: [
      { alternative_id: "a", class_id: "go", class_rank: 1, on_boundary: false, nearest_boundary_class_id: "go", distance_to_nearest_boundary: 0.2 },
      { alternative_id: "b", class_id: "go", class_rank: 1, on_boundary: false, nearest_boundary_class_id: "go", distance_to_nearest_boundary: 0.2 },
      { alternative_id: "c", class_id: "stop", class_rank: 2, on_boundary: false, nearest_boundary_class_id: "go", distance_to_nearest_boundary: 0.3 },
    ],
    audit_sample: { below_class_id: "go", seed: 7, requested_size: 1, pool_size: 1, alternative_ids: ["c"], selection_rule: "sha256(seed:alternative_id) ascending, then id" },
  },
  comparison: null, comparison_diagnostics: [],
};

/** The same model viewed as SMAA-2: 1000 draws, classes Go and Stop. */
export const smaaContext = resolveContext(project, "fp", { ...BASE_SELECTION, method: "smaa2" });
const est = (count: number, n = 1000) => ({ count, frequency: count / n, lower: Math.max(0, count / n - 0.03), upper: Math.min(1, count / n + 0.03) });
export const smaaRecord: SmaaAnalysisRecord = {
  record_version: "2", record_digest: "c".repeat(64), method: "smaa2", method_label: "SMAA-2 (sampled acceptability)",
  calculation_path: "smaa2.pcg64.v1", numerical_tolerance: 1e-12, csv_text_policy: "text-prefix-controls-v1",
  project_title: "P", scenario_name: "Base model", resolved_profile_name: "First profile",
  alternative_order: record.alternative_order, configuration: smaaContext.configuration,
  result: { method: "smaa2", schema_version: 3, project_id: "p1", project_fingerprint: "fp", configuration: smaaContext.configuration,
    weight_profile_id: "first", scenario_id: null, ranking: record.result.ranking, diagnostics: [], assumptions: ["Stated assumptions"],
    label: "sampled acceptability under these assumptions", run: "combined", evaluation: "sampled", samples: 1000, outcomes: null, seed: 4,
    algorithm: "smaa2.pcg64.v1", confidence: 0.95, interval_method: "clopper-pearson", dependence: "independent",
    uncertainty: { dependence: "independent", cells: [], groups: [{ parent_id: "g", kind: "unknown", intervals: {} }], shared_draws: [] },
    environment: { python: "3.12.15", numpy: "2.5.4", system: "Darwin arm64" },
    classes: [{ class_id: "go", name: "Go", rank: 1, lower_boundary: 0.5, upper_boundary: null }, { class_id: "stop", name: "Stop", rank: 2, lower_boundary: null, upper_boundary: 0.5 }],
    leader_id: "a",
    acceptability: [
      { alternative_id: "c", name: "C", ranks: [est(0), est(0), est(1000)], sole_first: est(0), tied_first: est(0), classes: { go: est(0), stop: est(1000) } },
      { alternative_id: "a", name: "Same", ranks: [est(620), est(380), est(0)], sole_first: est(600), tied_first: est(20), classes: { go: est(1000), stop: est(0) } },
      { alternative_id: "b", name: "Same", ranks: [est(400), est(600), est(0)], sole_first: est(380), tied_first: est(20), classes: { go: est(990), stop: est(10) } },
    ],
    inputs_to_check: [{ input: "local weight of Cost under G", path: "smaa.groups[g].cost", leader_rank1_upper_half: 0.8, leader_rank1_lower_half: 0.44, difference: 0.36 }],
    inputs_to_check_label: "heuristic: association in these draws, not causation or value of information",
  },
};

/** The same model viewed as PROMETHEE II. MAVT ties a and b and puts c last; PROMETHEE II puts a
 * first, c second and b last, so two pairs are ordered differently. b and c are incomparable. */
export const prometheeContext = resolveContext(project, "fp", { ...BASE_SELECTION, method: "promethee2" });
const flowLabel = "net outranking flows: these compare the alternatives with one another and are not preference values" as const;
export const prometheeRecord: PrometheeAnalysisRecord = {
  record_version: "2", record_digest: "d".repeat(64), method: "promethee2", method_label: "PROMETHEE II (outranking flows)",
  calculation_path: "promethee2.v1", numerical_tolerance: 1e-12, csv_text_policy: "text-prefix-controls-v1",
  project_title: "P", scenario_name: "Base model", resolved_profile_name: "First profile",
  alternative_order: record.alternative_order, configuration: prometheeContext.configuration,
  result: { method: "promethee2", schema_version: 4, project_id: "p1", project_fingerprint: "fp", configuration: prometheeContext.configuration,
    weight_profile_id: "first", scenario_id: null,
    ranking: [{ alternative_id: "a", name: "Same", rank: 1, value: 0.5 }, { alternative_id: "c", name: "C", rank: 2, value: -0.1 },
      { alternative_id: "b", name: "Same", rank: 3, value: -0.4 }],
    diagnostics: [{ severity: "info", code: "INCOMPARABLE_PAIRS", message: "PROMETHEE I finds 1 incomparable pair(s)", path: "" }],
    assumptions: ["Net outranking flows compare the alternatives with one another."],
    label: flowLabel, threshold_tolerance: "1e-12 * max(1, |x_a|, |x_b|)", leaf_order: ["cost", "quality"],
    criteria: [
      { criterion_id: "cost", name: "Cost", unit: "kg", direction: "minimise", weight: 2, normalised_weight: 2 / 3, function: { kind: "linear", q: 1, p: 3 }, coding: null },
      { criterion_id: "quality", name: "Quality", unit: "%", direction: "maximise", weight: 1, normalised_weight: 1 / 3, function: { kind: "usual" }, coding: null },
    ],
    flows: [
      { alternative_id: "a", name: "Same", rank: 1, positive_flow: 0.6, negative_flow: 0.1, net_flow: 0.5, criterion_flows: { cost: 0.75, quality: 0 } },
      { alternative_id: "c", name: "C", rank: 2, positive_flow: 0.3, negative_flow: 0.4, net_flow: -0.1, criterion_flows: { cost: 0, quality: -0.3 } },
      { alternative_id: "b", name: "Same", rank: 3, positive_flow: 0.35, negative_flow: 0.75, net_flow: -0.4, criterion_flows: { cost: -0.75, quality: 0.3 } },
    ],
    preference_matrix: { a: { a: 0, b: 0.7, c: 0.5 }, b: { a: 0.2, b: 0, c: 0.5 }, c: { a: 0, b: 0.3, c: 0 } },
    partial_order: [
      { alternative_a: "a", alternative_b: "c", relation: "preferred" },
      { alternative_a: "c", alternative_b: "b", relation: "incomparable" },
      { alternative_a: "a", alternative_b: "b", relation: "preferred" },
    ],
    explanation: { available: true, unavailable_reason: null, unavailable_codes: [], detail_limit: 1,
      ranks: [{ alternative_id: "a", name: "Same", mavt_rank: 1, promethee_rank: 1 }, { alternative_id: "c", name: "C", mavt_rank: 3, promethee_rank: 2 },
        { alternative_id: "b", name: "Same", mavt_rank: 1, promethee_rank: 3 }],
      pairs: [
        { alternative_a: "b", alternative_b: "a", mavt_rank_a: 1, mavt_rank_b: 1, promethee_rank_a: 3, promethee_rank_b: 1, value_gap: 0,
          flow_gap: -0.9, head_to_head: -0.5, via_others: -0.4, detailed: true,
          criteria: [
            { criterion_id: "cost", name: "Cost", difference: -4, favours: "a", zone: "full", preference_degree: 1, capped: true, q: 1, p: 3,
              promethee_contribution: -1, promethee_head_to_head: -0.6667, mavt_contribution: -0.1 },
            { criterion_id: "quality", name: "Quality", difference: 2, favours: "b", zone: "full", preference_degree: 1, capped: true, q: null, p: null,
              promethee_contribution: 0.1, promethee_head_to_head: 0.1667, mavt_contribution: 0.1 },
          ],
          reasons: ["Cost: favours Same in PROMETHEE (-1 of the flow gap); Same is 4 kg lower, beyond p = 3, so PROMETHEE counts full preference and no more."] },
        { alternative_a: "b", alternative_b: "c", mavt_rank_a: 1, mavt_rank_b: 3, promethee_rank_a: 3, promethee_rank_b: 2, value_gap: 0.5,
          flow_gap: -0.3, head_to_head: 0.2, via_others: -0.5, detailed: false, criteria: [], reasons: [] },
      ] },
  },
};

/** The same model viewed as AHP: criteria cost and quality under g, alternatives judged on each leaf.
 * The alternatives' matrix on quality is inconsistent. */
export const ahpContext = resolveContext(project, "fp", { ...BASE_SELECTION, method: "ahp" });
const ahpLabel = "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT values or swing weights" as const;
const triad = { items: ["c", "a", "b"] as [string, string, string], judgements: [9, 5, 1 / 3] as [number, number, number], index: 1 - (1 / 3) / 45, consistent_value: 45 };
export const ahpRecord: AhpAnalysisRecord = {
  record_version: "2", record_digest: "e".repeat(64), method: "ahp", method_label: "AHP (pairwise priorities)",
  calculation_path: "ahp.eigen_power.v1", numerical_tolerance: 1e-12, csv_text_policy: "text-prefix-controls-v1",
  project_title: "P", scenario_name: "", resolved_profile_name: "",
  alternative_order: record.alternative_order, configuration: ahpContext.configuration,
  result: { method: "ahp", schema_version: 5, project_id: "p1", project_fingerprint: "fp", configuration: ahpContext.configuration,
    weight_profile_id: null, scenario_id: null,
    ranking: [{ alternative_id: "a", name: "Same", rank: 1, value: 0.5 }, { alternative_id: "c", name: "C", rank: 2, value: 0.3 },
      { alternative_id: "b", name: "Same", rank: 3, value: 0.2 }],
    diagnostics: [{ severity: "warning", code: "AHP_INCONSISTENT", message: "consistency ratio 0.700 is above 0.10", path: "ahp.alternatives[quality]" }],
    assumptions: ["Priorities are the principal eigenvectors of the stated pairwise matrices."],
    label: ahpLabel, synthesis: "distributive", random_index_table: "saaty-tran-2007",
    random_indices: [0, 0, 0.52, 0.89, 1.11, 1.25, 1.35, 1.4, 1.45, 1.49, 1.52, 1.54, 1.56, 1.58, 1.59],
    consistency_threshold: 0.1, tolerance: 1e-14, max_iterations: 10000, leaf_order: ["cost", "quality"],
    local_priorities: { g: 1, cost: 0.75, quality: 0.25 }, global_priorities: { cost: 0.75, quality: 0.25 },
    matrices: [
      { kind: "criteria", group_id: "g", items: ["cost", "quality"], judgements: [{ row: "cost", column: "quality", value: 3 }],
        priorities: { cost: 0.75, quality: 0.25 }, lambda_max: 2, consistency_index: 0, random_index: 0, consistency_ratio: 0,
        inconsistent: false, most_inconsistent_triad: null, iterations: 0 },
      { kind: "alternatives", group_id: "cost", items: ["c", "a", "b"], judgements: [], priorities: { c: 0.3, a: 0.5, b: 0.2 },
        lambda_max: 3, consistency_index: 0, random_index: 0.52, consistency_ratio: 0, inconsistent: false,
        most_inconsistent_triad: { ...triad, index: 0, consistent_value: 1 }, iterations: 2 },
      { kind: "alternatives", group_id: "quality", items: ["c", "a", "b"], judgements: [], priorities: { c: 0.3, a: 0.5, b: 0.2 },
        lambda_max: 3.728, consistency_index: 0.364, random_index: 0.52, consistency_ratio: 0.7, inconsistent: true,
        most_inconsistent_triad: triad, iterations: 30 },
    ],
    alternatives: [
      { alternative_id: "a", name: "Same", rank: 1, priority: 0.5, ideal_score: null, local_priorities: { cost: 0.5, quality: 0.5 }, weighted_parts: { cost: 0.375, quality: 0.125 } },
      { alternative_id: "c", name: "C", rank: 2, priority: 0.3, ideal_score: null, local_priorities: { cost: 0.3, quality: 0.3 }, weighted_parts: { cost: 0.225, quality: 0.075 } },
      { alternative_id: "b", name: "Same", rank: 3, priority: 0.2, ideal_score: null, local_priorities: { cost: 0.2, quality: 0.2 }, weighted_parts: { cost: 0.15, quality: 0.05 } },
    ] },
};
