import type { Issue, ValidationReport } from "../api/types";

export type IssueTarget =
  | { kind: "criterion"; id: string }
  | { kind: "performance"; alternativeId: string; criterionId: string }
  | { kind: "judgement"; nodeId: string | null }
  | { kind: "scenario"; id: string }
  | { kind: "sorting" }
  | { kind: "uncertainty" }
  | { kind: "outranking" }
  | { kind: "pairwise" }
  | { kind: "requirements" }
  | { kind: "project" };

/** Where an issue's `path` (as produced by the engine's validation) points in the editor. */
export function parseIssuePath(path: string): IssueTarget {
  let m = /^criteria\[([^\]]+)\]/.exec(path);
  if (m?.[1]) return { kind: "criterion", id: m[1] };
  m = /^performances\[([^,\]]+),([^\]]+)\]/.exec(path);
  if (m?.[1] && m[2]) return { kind: "performance", alternativeId: m[1], criterionId: m[2] };
  m = /^weight_profiles\[[^\]]+\]\.judgements(?:\.(.+))?$/.exec(path);
  if (m) return { kind: "judgement", nodeId: m[1] ?? null };
  m = /^scenarios\[([^\]]+)\]/.exec(path);
  if (m?.[1]) return { kind: "scenario", id: m[1] };
  if (path === "sorting" || path.startsWith("sorting.")) return { kind: "sorting" };
  if (path === "smaa" || path.startsWith("smaa.")) return { kind: "uncertainty" };
  if (path === "promethee" || path.startsWith("promethee.")) return { kind: "outranking" };
  if (path === "ahp" || path.startsWith("ahp.")) return { kind: "pairwise" };
  if (path === "requirements" || path.startsWith("requirements")) return { kind: "requirements" };
  return { kind: "project" };
}

export function errorsOf(report: ValidationReport): Issue[] {
  return report.issues.filter((i) => i.severity === "error");
}

export function warningsOf(report: ValidationReport): Issue[] {
  return report.issues.filter((i) => i.severity === "warning");
}

export function issuesForCriterion(report: ValidationReport, id: string): Issue[] {
  return report.issues.filter((i) => {
    const t = parseIssuePath(i.path);
    return t.kind === "criterion" && t.id === id;
  });
}

export function issuesForPerformance(
  report: ValidationReport,
  alternativeId: string,
  criterionId: string,
): Issue[] {
  return report.issues.filter((i) => {
    const t = parseIssuePath(i.path);
    return (
      t.kind === "performance" && t.alternativeId === alternativeId && t.criterionId === criterionId
    );
  });
}

export function issuesForJudgement(report: ValidationReport, nodeId: string): Issue[] {
  return report.issues.filter((i) => {
    const t = parseIssuePath(i.path);
    return t.kind === "judgement" && t.nodeId === nodeId;
  });
}

/** Does this criterion, or anything beneath it, have an error? (for tree badges) */
export function criterionHasError(
  report: ValidationReport,
  id: string,
  subtree: readonly string[],
): boolean {
  const ids = new Set(subtree.length ? subtree : [id]);
  return report.issues.some((i) => {
    if (i.severity !== "error") return false;
    const t = parseIssuePath(i.path);
    if (t.kind === "criterion") return ids.has(t.id);
    if (t.kind === "performance") return ids.has(t.criterionId);
    if (t.kind === "judgement") return t.nodeId !== null && ids.has(t.nodeId);
    return false;
  });
}

export type EditorTab = "project" | "model" | "alternatives" | "measurements" | "weights" | "scenarios" | "requirements" | "classes" | "uncertainty" | "outranking" | "pairwise" | "sensitivity" | "results" | "compare" | "questions" | "evidence" | "decision";

/** The tab that can fix an issue (used by "click an issue to go to it"). */
export function tabForIssue(issue: Issue): EditorTab {
  const t = parseIssuePath(issue.path);
  switch (t.kind) {
    case "criterion":
      return "model";
    case "performance":
      return "measurements";
    case "judgement":
      return "weights";
    case "scenario":
      return "scenarios";
    case "sorting":
      return "classes";
    case "uncertainty":
      return "uncertainty";
    case "outranking":
      return "outranking";
    case "pairwise":
      return "pairwise";
    case "requirements":
      return "requirements";
    case "project":
      break;
  }
  switch (issue.code) {
    case "NO_ALTERNATIVES":
    case "SINGLE_ALTERNATIVE":
    case "DUPLICATE_ALTERNATIVE_ID":
    case "DUPLICATE_ALTERNATIVE_NAME":
    case "PROMETHEE_TOO_FEW_ALTERNATIVES":
    case "AHP_TOO_FEW_ALTERNATIVES":
      return "alternatives";
    case "NO_CRITERIA":
    case "INVALID_TREE":
      return "model";
    case "NO_WEIGHT_PROFILE":
    case "UNSUPPORTED_WEIGHT_METHOD":
    case "UNKNOWN_PROFILE":
      return "weights";
    default:
      return "project";
  }
}
