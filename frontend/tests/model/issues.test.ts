import { describe, expect, it } from "vitest";
import type { Issue, ValidationReport } from "../../src/api/types";
import {
  criterionHasError,
  errorsOf,
  issuesForCriterion,
  issuesForJudgement,
  issuesForPerformance,
  parseIssuePath,
  tabForIssue,
  warningsOf,
} from "../../src/model/issues";

const issue = (severity: Issue["severity"], code: string, path: string): Issue => ({ severity, code, message: code, path });

describe("parseIssuePath (the engine's path vocabulary)", () => {
  it.each([
    ["criteria[cost]", { kind: "criterion", id: "cost" }],
    ["criteria[cost].scale", { kind: "criterion", id: "cost" }],
    ["performances[alt_1,cost]", { kind: "performance", alternativeId: "alt_1", criterionId: "cost" }],
    ["weight_profiles[default].judgements.team", { kind: "judgement", nodeId: "team" }],
    ["weight_profiles[default].judgements", { kind: "judgement", nodeId: null }],
    ["scenarios[s1].value_function_overrides[size]", { kind: "scenario", id: "s1" }],
    ["alternatives", { kind: "project" }],
    ["", { kind: "project" }],
  ])("%s", (path, expected) => {
    expect(parseIssuePath(path)).toEqual(expected);
  });
});

describe("tabForIssue", () => {
  it.each([
    [issue("error", "MISSING_SCALE", "criteria[a]"), "model"],
    [issue("error", "MISSING_MEASUREMENT", "performances[x,a]"), "measurements"],
    [issue("error", "MISSING_JUDGEMENT", "weight_profiles[p].judgements.a"), "weights"],
    [issue("warning", "LOCAL_ANCHORS", "scenarios[s].value_function_overrides[a]"), "scenarios"],
    [issue("error", "NO_ALTERNATIVES", ""), "alternatives"],
    [issue("error", "NO_CRITERIA", ""), "model"],
    [issue("error", "NO_WEIGHT_PROFILE", ""), "weights"],
    [issue("error", "SOMETHING_ELSE", ""), "project"],
  ] as const)("%j", (i, tab) => {
    expect(tabForIssue(i)).toBe(tab);
  });
});

describe("filters", () => {
  const report: ValidationReport = {
    issues: [
      issue("error", "MISSING_SCALE", "criteria[a]"),
      issue("warning", "LOCAL_ANCHORS", "criteria[a]"),
      issue("error", "MISSING_MEASUREMENT", "performances[x,b]"),
      issue("error", "MISSING_JUDGEMENT", "weight_profiles[p].judgements.c"),
      issue("warning", "X", ""),
    ],
  };

  it("splits by severity", () => {
    expect(errorsOf(report)).toHaveLength(3);
    expect(warningsOf(report)).toHaveLength(2);
  });

  it("selects by target", () => {
    expect(issuesForCriterion(report, "a")).toHaveLength(2);
    expect(issuesForCriterion(report, "b")).toHaveLength(0);
    expect(issuesForPerformance(report, "x", "b")).toHaveLength(1);
    expect(issuesForPerformance(report, "y", "b")).toHaveLength(0);
    expect(issuesForJudgement(report, "c")).toHaveLength(1);
  });

  it("a group shows an error badge if anything beneath it has one, but not for warnings", () => {
    expect(criterionHasError(report, "g", ["g", "a"])).toBe(true);
    expect(criterionHasError(report, "g", ["g", "b"])).toBe(true);
    expect(criterionHasError(report, "g", ["g", "c"])).toBe(true);
    expect(criterionHasError(report, "g", ["g", "other"])).toBe(false);
    const warnOnly: ValidationReport = { issues: [issue("warning", "LOCAL_ANCHORS", "criteria[a]")] };
    expect(criterionHasError(warnOnly, "a", ["a"])).toBe(false);
    expect(criterionHasError(report, "a", [])).toBe(true); // empty subtree means the node itself
  });
});
