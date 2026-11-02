import { useCallback, useMemo } from "react";
import { api } from "../api/client";
import { isAhpRecord, isPrometheeRecord, isSmaaRecord, type AnalysisConfiguration, type AnyAnalysisRecord, type Project, type ValidationReport } from "../api/types";
import { errorsOf } from "../model/issues";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/** Criterion selection is presentation state, so it never causes a second mathematical evaluation. */
export function useAnalysisRecord(project: Project, validation: ValidationReport, context: AnalysisContext) {
  const key = analysisKey({ ...context, criterionId: null }, "analysis-record", context.resolvedProfileId);
  const serialized = canonical(context.configuration);
  const configuration = useMemo(() => JSON.parse(serialized) as AnalysisConfiguration, [serialized]);
  const { fingerprint, resolvedProfileId, scenarioId } = context;
  const load = useCallback(async (signal: AbortSignal) => {
    const record = await api.analysisRecord(project, configuration, signal);
    assertAnalysisRecord(record, project, fingerprint, configuration, resolvedProfileId, scenarioId);
    return record;
  }, [project, configuration, fingerprint, resolvedProfileId, scenarioId]);
  const errors = errorsOf(validation).length;
  const request = useAnalysisRequest(key, errors === 0, load);
  return errors ? { status: "blocked" as const, errors } : request;
}

export function assertAnalysisRecord(record: AnyAnalysisRecord, project: Project, fingerprint: string,
  configuration: AnalysisConfiguration, profile: string | null, scenario: string | null) {
  const common = record.result;
  // Version 1 records hold MAVT only; every other method's record is version 2.
  const expectedVersion = configuration.method === "mavt" ? "1" : "2";
  // AHP reads no weight profile or scenario, so its results name neither.
  const reads = configuration.method !== "ahp";
  if (record.record_version !== expectedVersion || !/^[a-f0-9]{64}$/.test(record.record_digest) ||
      common.method !== configuration.method || common.project_id !== project.id || common.project_fingerprint !== fingerprint ||
      common.weight_profile_id !== (reads ? profile : null) || common.scenario_id !== (reads ? scenario : null) ||
      canonical(common.configuration) !== canonical(configuration))
    throw Error("Analysis record does not match the selected project, revision, scenario and profile.");
  const ids = project.alternatives.map(a => a.id);
  const rankedIds = common.ranking.map(a => a.alternative_id);
  if (isSmaaRecord(record)) {
    // Acceptabilities: one row per alternative in project order, one entry per rank and class.
    const rows = record.result.acceptability;
    const classIds = record.result.classes.map(c => c.class_id);
    if (canonical(record.alternative_order) !== canonical(ids) || canonical([...rankedIds].sort()) !== canonical([...ids].sort()) ||
        canonical(rows.map(a => a.alternative_id)) !== canonical(ids) || !ids.includes(record.result.leader_id) ||
        rows.some(a => a.ranks.length !== ids.length || canonical(Object.keys(a.classes).sort()) !== canonical([...classIds].sort())))
      throw Error("Acceptabilities do not match the project's alternatives and classes.");
    return;
  }
  if (isAhpRecord(record)) {
    // Priorities: one row per alternative in the ranking's order, whose value is the priority; one
    // local priority per leaf; every judged group and leaf has its matrix.
    const result = record.result;
    const rows = result.alternatives;
    const leaves = canonical([...result.leaf_order].sort());
    const leafMatrices = result.matrices.filter(m => m.kind === "alternatives").map(m => m.group_id);
    if (canonical(record.alternative_order) !== canonical(ids) || canonical(rows.map(a => a.alternative_id)) !== canonical(rankedIds) ||
        canonical([...rankedIds].sort()) !== canonical([...ids].sort()) ||
        rows.some((a, i) => { const ranked = common.ranking[i];
          return !ranked || ranked.value !== a.priority || ranked.rank !== a.rank || canonical(Object.keys(a.local_priorities).sort()) !== leaves; }) ||
        canonical(leafMatrices) !== canonical(result.leaf_order) ||
        result.matrices.some(m => m.kind === "alternatives" && canonical(m.items) !== canonical(ids)))
      throw Error("AHP priorities do not match the project's alternatives and criteria.");
    return;
  }
  if (isPrometheeRecord(record)) {
    // Flows: one row per alternative in the ranking's order, whose value is the net flow; one
    // single-criterion flow per leaf; every unordered pair once in the partial order.
    const result = record.result;
    const flowIds = result.flows.map(f => f.alternative_id);
    const leaves = canonical([...result.leaf_order].sort());
    const pairs = result.partial_order.map(p => [p.alternative_a, p.alternative_b].sort().join("\u0000"));
    const explained = result.explanation.available ? result.explanation.ranks.map(r => r.alternative_id) : flowIds;
    if (canonical(record.alternative_order) !== canonical(ids) || canonical(flowIds) !== canonical(rankedIds) ||
        canonical([...flowIds].sort()) !== canonical([...ids].sort()) || canonical(explained) !== canonical(flowIds) ||
        result.flows.some((f, i) => { const ranked = common.ranking[i];
          return !ranked || ranked.value !== f.net_flow || ranked.rank !== f.rank || canonical(Object.keys(f.criterion_flows).sort()) !== leaves; }) ||
        canonical(result.criteria.map(c => c.criterion_id)) !== canonical(result.leaf_order) ||
        new Set(pairs).size !== pairs.length || pairs.length !== ids.length * (ids.length - 1) / 2)
      throw Error("Outranking flows do not match the project's alternatives and criteria.");
    return;
  }
  const result = record.result;
  if (canonical(record.alternative_order) !== canonical(ids) ||
      canonical([...rankedIds].sort()) !== canonical([...ids].sort()) ||
      canonical(result.alternatives.map(a => a.alternative_id).sort()) !== canonical([...ids].sort()) ||
      canonical(record.criteria.map(c => c.criterion_id)) !== canonical(result.leaf_order))
    throw Error("Analysis record identifiers do not match the project.");
  const leaves = [...result.leaf_order].sort();
  for (const alt of result.alternatives) {
    const ranked = result.ranking.find(a => a.alternative_id === alt.alternative_id);
    if (!ranked || ranked.rank !== alt.rank || ranked.value !== alt.overall_value ||
        record.contribution_totals[alt.alternative_id] !== alt.overall_value ||
        [alt.raw_measurements, alt.partial_values, alt.weighted_contributions].some(values => canonical(Object.keys(values).sort()) !== canonical(leaves)))
      throw Error("Analysis detail does not match the completed ranking and criteria.");
  }
  if (record.record_version === "2") {
    const classes = record.result.classes;
    const classIds = classes.map(c => c.class_id);
    const assigned = record.result.assignments.map(a => a.alternative_id);
    if (classes.some((c, i) => c.rank !== i + 1) ||
        canonical([...assigned].sort()) !== canonical([...ids].sort()) || new Set(assigned).size !== assigned.length ||
        record.result.assignments.some(a => classIds[a.class_rank - 1] !== a.class_id) ||
        canonical(classes.flatMap(c => c.alternative_ids).sort()) !== canonical([...ids].sort()))
      throw Error("Class assignments do not match this analysis record.");
  }
  if (canonical(Object.keys(record.dominance_relations).sort()) !== canonical([...ids].sort()) ||
      Object.values(record.dominance_relations).some(row => canonical(Object.keys(row).sort()) !== canonical([...ids].sort())))
    throw Error("Dominance identifiers do not match this analysis record.");
  const comparison = record.comparison;
  if (comparison) {
    const selected = comparison.scenarios[0];
    const baseProfile = configuration.weight_profile_id ?? project.weight_profiles[0]?.id ?? null;
    for (const outcome of [comparison.baseline, ...comparison.scenarios]) {
      if ([outcome.values, outcome.rank_by_alternative, outcome.delta_from_baseline].some(values => canonical(Object.keys(values).sort()) !== canonical([...ids].sort())))
        throw Error("Comparison alternatives do not match this analysis record.");
    }
    if (comparison.project_fingerprint !== fingerprint || canonical(comparison.configuration) !== canonical(configuration) ||
        canonical(comparison.scenario_ids) !== canonical([scenario]) || comparison.scenarios.length !== 1 ||
        comparison.baseline.scenario_id !== null || comparison.baseline.weight_profile_id !== baseProfile ||
        canonical(comparison.baseline.configuration) !== canonical({ ...configuration, scenario_id: null }) ||
        !selected || selected.scenario_id !== scenario || selected.weight_profile_id !== profile ||
        canonical(selected.configuration) !== canonical(configuration) ||
        result.ranking.some(a => selected.values[a.alternative_id] !== a.value || selected.rank_by_alternative[a.alternative_id] !== a.rank))
      throw Error("Comparison does not belong to this completed analysis record.");
  }
}
