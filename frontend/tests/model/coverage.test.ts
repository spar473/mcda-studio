import { expect, it } from "vitest";
import type { Issue } from "../../src/api/types";
import { buildCoverage, coverageCell, coveragePage, coverageSummary, pagesForCell, pairKey, reconcileCoverageCell } from "../../src/model/coverage";
import { visibleRows } from "../../src/model/visibleTree";
import { node, ordinalScale, projectWith, ratioScale } from "../fixtures";

const linear = { kind: "linear", direction: "increasing", out_of_domain: "error" } as const;
const alternatives = [{ id: "x", name: "Option", metadata: {} }];
const numeric = node("number", "group", 0, { scale: ratioScale, value_function: linear });
const labelled = node("label", "group", 1, { scale: ordinalScale, value_function: { kind: "qualitative", mapping: { Low: 0, Mid: 0.5, High: 1 } } });
const pair = { alternativeId: "x", criterionId: "number" };
const issue = (path: string, code = "TEST", severity: Issue["severity"] = "error"): Issue => ({ path, code, severity, message: code });

it("counts numeric zero and qualitative labels as entered without interpreting their value", () => {
  const index = buildCoverage(projectWith([node("group"), numeric, labelled], { alternatives, performances: [
    { alternative_id: "x", criterion_id: "number", value: 0 }, { alternative_id: "x", criterion_id: "label", value: "Low" },
  ] }), { issues: [] });
  expect([index.entered, index.expected, index.missing]).toEqual([2, 2, 0]);
  expect(coverageCell(index, pair)).toMatchObject({ entered: true, status: "Entered", value: 0 });
  expect(coverageCell(index, { ...pair, criterionId: "label" }).value).toBe("Low");
});

it("counts all structural leaves even when their branches are collapsed", () => {
  const index = buildCoverage(projectWith([node("group"), numeric, labelled, node("other")], { alternatives }), { issues: [] });
  expect(visibleRows(index.tree, new Set(["group"]), null).rows.map(r => r.node.id)).toEqual(["group", "other"]);
  expect(index.leaves.map(n => n.id)).toEqual(["number", "label", "other"]);
  expect(index.expected).toBe(3); expect(index.missing).toBe(3);
});

it("counts distinct known pairs, excluding duplicate rows, orphan references and measurements on branches", () => {
  const index = buildCoverage(projectWith([node("group"), numeric, labelled], { alternatives, performances: [
    { alternative_id: "x", criterion_id: "number", value: 0 }, { alternative_id: "x", criterion_id: "number", value: 1 },
    { alternative_id: "ghost", criterion_id: "label", value: "Low" }, { alternative_id: "x", criterion_id: "gone", value: 2 },
    { alternative_id: "x", criterion_id: "group", value: 3 },
  ] }), { issues: [issue("performances[x,number]", "DUPLICATE_PERFORMANCE")] });
  expect([index.expected, index.entered, index.missing, index.attention]).toEqual([2, 1, 1, 1]);
  expect(index.measurements.size).toBe(1);
});

it.each([projectWith([]), projectWith([numeric]), projectWith([], { alternatives })])("an empty matrix never reads as complete or 100 percent", project => {
  const index = buildCoverage(project, { issues: [] });
  expect(index.expected).toBe(0); expect(index.entered).toBe(0);
  expect(coverageSummary(index)).toBe("Add alternatives/criteria · 0 expected cells");
  expect(coverageSummary(index)).not.toMatch(/100%|complete/i);
});

it("keeps presence, cell attention, criterion setup and preference issues independent", () => {
  const index = buildCoverage(projectWith([node("group"), numeric, labelled], { alternatives, performances: [
    { alternative_id: "x", criterion_id: "number", value: 0 },
  ] }), { issues: [issue("performances[x,number]", "OUT_OF_DOMAIN"), issue("performances[x,number]", "CLAMPED", "warning"),
    issue("performances[x,label]", "MISSING_MEASUREMENT"), issue("criteria[label]", "MISSING_ANCHORS"),
    issue("weight_profiles[p].judgements.group", "MISSING_JUDGEMENT"), issue("", "NO_WEIGHT_PROFILE"), issue("", "OTHER")] });
  expect(coverageCell(index, pair).status).toBe("Entered · needs attention");
  expect(coverageCell(index, { ...pair, criterionId: "label" }).status).toBe("Missing · setup needed");
  expect(index.attention).toBe(1); expect(index.preferenceIssues).toHaveLength(2);
  expect(coverageSummary(index)).toBe("1/2 entered; 1 missing; 1 entered cell needs attention");
});

it("does not infer a cell issue from a criterion-level engine error or absence of cell issues", () => {
  const index = buildCoverage(projectWith([node("n")], { alternatives, performances: [{ alternative_id: "x", criterion_id: "n", value: 0 }] }),
    { issues: [issue("criteria[n]", "MISSING_SCALE")] });
  expect(coverageCell(index, { ...pair, criterionId: "n" }).status).toBe("Entered · setup needed");
  expect(index.attention).toBe(0);
});

it("an unconfigured criterion may be Missing with setup needed even when validation stopped early", () => {
  const index = buildCoverage(projectWith([node("n")], { alternatives }), { issues: [] });
  expect(coverageCell(index, { ...pair, criterionId: "n" }).status).toBe("Missing · setup needed");
});

it("preserves selection through renames and clears it when an ID disappears or a leaf becomes a branch", () => {
  const build = (criteria = [node("number")], alts = alternatives) => buildCoverage(projectWith(criteria, { alternatives: alts }), { issues: [] });
  expect(reconcileCoverageCell(build([node("number", null, 0, { name: "Renamed" })], [{ id: "x", name: "Renamed option", metadata: {} }]), pair)).toBe(pair);
  expect(reconcileCoverageCell(build([], alternatives), pair)).toBeNull();
  expect(reconcileCoverageCell(build([node("number")], []), pair)).toBeNull();
  expect(reconcileCoverageCell(build([node("number"), node("child", "number")]), pair)).toBeNull();
  expect(reconcileCoverageCell(build(), null)).toBeNull();
});

it.each([[0, 0, 0, 0], [20, 0, 0, 20], [21, 1, 20, 21], [40, 1, 20, 40], [41, 2, 40, 41], [41, 9, 40, 41], [41, -1, 0, 20]])(
  "pages %i items at page %i without gaps or phantom last rows", (total, requested, start, end) => {
    expect(coveragePage(total, requested)).toMatchObject({ start, end });
  });

it("finds both page boundaries by stable ID, including the final 100 by 100 cell", () => {
  const index = buildCoverage(projectWith(Array.from({ length: 100 }, (_, i) => node(`c${String(i)}`, null, i)), {
    alternatives: Array.from({ length: 100 }, (_, i) => ({ id: `a${String(i)}`, name: "Option", metadata: {} })),
  }), { issues: [] });
  expect(pagesForCell(index, { alternativeId: "a19", criterionId: "c20" })).toEqual({ row: 0, column: 1 });
  expect(pagesForCell(index, { alternativeId: "a99", criterionId: "c99" })).toEqual({ row: 4, column: 4 });
  expect(index.expected).toBe(10000);
});

it("pair keys cannot collide when defensive incoming IDs contain delimiters", () => {
  expect(pairKey({ alternativeId: "a|b", criterionId: "c" })).not.toBe(pairKey({ alternativeId: "a", criterionId: "b|c" }));
});

it("links an identical engine issue once even when full-draft scenario validation repeats it", () => {
  const problem = issue("performances[x,n]", "MISSING_MEASUREMENT");
  const index = buildCoverage(projectWith([node("n")], { alternatives }), { issues: [problem, { ...problem }] });
  expect(coverageCell(index, { ...pair, criterionId: "n" }).issues).toEqual([problem]);
});
