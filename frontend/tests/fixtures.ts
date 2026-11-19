import type { CriterionNode, Meta, Project, ProjectDocument, Scale } from "../src/api/types";

export const META: Meta = {
  scale_types: [
    { type: "categorical", numeric: false, labelled: true, allowed_value_functions: ["qualitative"] },
    { type: "ordinal", numeric: false, labelled: true, allowed_value_functions: ["qualitative"] },
    { type: "interval", numeric: true, labelled: false, allowed_value_functions: ["linear", "piecewise_linear", "direct_rating"] },
    { type: "ratio", numeric: true, labelled: false, allowed_value_functions: ["linear", "piecewise_linear"] },
  ],
  value_function_kinds: ["linear", "piecewise_linear", "qualitative", "direct_rating"],
  anchor_modes: ["fixed", "local"],
  directions: ["increasing", "decreasing"],
  out_of_domain_policies: ["error", "clamp"],
  methods: [
    {
      name: "ahp",
      label: "AHP (pairwise priorities)",
      capabilities: ["consistency"],
      export_tables: ["priorities", "criterion_priorities", "local_priorities", "consistency"],
    },
    {
      name: "mavt",
      label: "MAVT (additive value)",
      capabilities: ["contributions", "scenario_comparison", "swing_weights", "value_functions", "value_scores", "weight_sensitivity"],
      export_tables: ["ranking", "contributions", "partial_values", "dominance", "comparison"],
    },
    {
      name: "mavt_sorting",
      label: "Value-based sorting (MAVT)",
      capabilities: ["classes", "contributions", "scenario_comparison", "swing_weights", "value_functions", "value_scores", "weight_sensitivity"],
      export_tables: ["ranking", "classes", "contributions", "partial_values", "dominance", "comparison"],
    },
    {
      name: "promethee2",
      label: "PROMETHEE II (outranking flows)",
      capabilities: ["flows"],
      export_tables: ["flows", "criterion_flows", "partial_order", "explanation"],
    },
    {
      name: "smaa2",
      label: "SMAA-2 (sampled acceptability)",
      capabilities: ["acceptability", "swing_weights", "value_functions"],
      export_tables: ["rank_acceptability", "class_acceptability", "inputs_to_check"],
    },
  ],
};

export function node(
  id: string,
  parent: string | null = null,
  order = 0,
  extra: Partial<CriterionNode> = {},
): CriterionNode {
  return { id, name: id.toUpperCase(), parent_id: parent, order, description: "", scale: null, value_function: null, ...extra };
}

export const ratioScale: Scale = { type: "ratio", unit: "kg", lower: 0, upper: 10, anchor_mode: "fixed", labels: [] };
export const ordinalScale: Scale = { type: "ordinal", unit: null, lower: null, upper: null, anchor_mode: "fixed", labels: ["Low", "Mid", "High"] };

/**
 *   a ── a1 (ratio, measured)
 *    └── a2
 *   b ── b1 ── b1x
 *    └── b2
 *   c
 */
export function sampleProject(): Pick<Project, "criteria" | "performances"> {
  return {
    criteria: [
      node("a", null, 0),
      node("a1", "a", 0, { scale: ratioScale, value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } }),
      node("a2", "a", 1),
      node("b", null, 1),
      node("b1", "b", 0),
      node("b1x", "b1", 0),
      node("b2", "b", 1),
      node("c", null, 2),
    ],
    performances: [{ alternative_id: "x", criterion_id: "a1", value: 4 }],
  };
}

export function projectWith(criteria: CriterionNode[], extra: Partial<Project> = {}): Project {
  return {
    schema_version: 1,
    id: "p1",
    title: "P",
    description: "",
    decision_maker: "",
    alternatives: [],
    criteria,
    performances: [],
    weight_profiles: [],
    scenarios: [],
    analysis: { method: "mavt" },
    provenance: [],
    ...extra,
  } as unknown as Project;
}

export function doc(fingerprint: string, project: Project = projectWith([]), issues: ProjectDocument["validation"]["issues"] = []): ProjectDocument {
  return { project, fingerprint, updated_at: null, validation: { issues } };
}
