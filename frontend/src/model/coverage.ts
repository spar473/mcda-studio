// Read-only draft facts. Presence never implies validity or evidence acceptance.
import type { Issue, Measurement, Project, ValidationReport } from "../api/types";
import { leafIds } from "./diagram";
import { parseIssuePath } from "./issues";
import { indexTree } from "./visibleTree";

export interface CoverageCell { alternativeId: string; criterionId: string }
export const COVERAGE_PAGE_SIZE = 20;
// Encoding both IDs keeps distinct pairs distinct even for defensive incoming data.
export const pairKey = (cell: CoverageCell) => JSON.stringify([cell.alternativeId, cell.criterionId]);

/** Build once per accepted draft/validation revision, never once per cell or collapse. */
export function buildCoverage(project: Project, validation: ValidationReport) {
  const tree = indexTree(project.criteria);
  const alternatives = [...new Map(project.alternatives.map(a => [a.id, a])).values()];
  const leaves = leafIds(tree).flatMap(id => {
    const node = tree.byId.get(id); return node ? [node] : [];
  });
  const alternativePositions = new Map(alternatives.map((a, i) => [a.id, i]));
  const leafPositions = new Map(leaves.map((n, i) => [n.id, i]));
  const measurements = new Map<string, Measurement>();
  for (const performance of project.performances) {
    if (!alternativePositions.has(performance.alternative_id) || !leafPositions.has(performance.criterion_id)) continue;
    const key = pairKey({ alternativeId: performance.alternative_id, criterionId: performance.criterion_id });
    // Duplicate rows contribute one known pair, never extra entered cells. Validation retains them.
    measurements.set(key, performance.value);
  }
  const pairIssues = new Map<string, Issue[]>();
  const criterionIssues = new Map<string, Issue[]>();
  const preferenceIssues: Issue[] = [];
  const seenIssues = new Set<string>();
  for (const issue of validation.issues) {
    // Full-draft validation can repeat an identical base issue while checking scenarios.
    const identity = JSON.stringify([issue.severity, issue.code, issue.path, issue.message]);
    if (seenIssues.has(identity)) continue;
    seenIssues.add(identity);
    const target = parseIssuePath(issue.path);
    if (target.kind === "performance") {
      const key = pairKey(target);
      const issues = pairIssues.get(key) ?? []; issues.push(issue); pairIssues.set(key, issues);
    } else if (target.kind === "criterion") {
      const issues = criterionIssues.get(target.id) ?? []; issues.push(issue); criterionIssues.set(target.id, issues);
    }
    if (target.kind === "judgement" || issue.path.startsWith("weight_profiles") ||
        ["NO_WEIGHT_PROFILE", "UNKNOWN_PROFILE", "UNSUPPORTED_WEIGHT_METHOD"].includes(issue.code)) preferenceIssues.push(issue);
  }
  // Only presence checks and engine-reported model errors; no scale/function rules are recreated.
  const setupIds = new Set(leaves.filter(n => !n.scale || !n.value_function ||
    criterionIssues.get(n.id)?.some(i => i.severity === "error")).map(n => n.id));
  const expected = alternatives.length * leaves.length;
  const entered = measurements.size;
  let attention = 0;
  for (const key of measurements.keys()) if (pairIssues.get(key)?.length) attention++;
  return { tree, alternatives, leaves, alternativePositions, leafPositions, measurements, pairIssues,
    criterionIssues, preferenceIssues, setupIds, expected, entered, missing: expected - entered, attention };
}
export type CoverageIndex = ReturnType<typeof buildCoverage>;

export function coverageCell(index: CoverageIndex, cell: CoverageCell) {
  const key = pairKey(cell);
  const entered = index.measurements.has(key);
  const issues = index.pairIssues.get(key) ?? [];
  const setup = index.setupIds.has(cell.criterionId);
  const status = `${entered ? "Entered" : "Missing"}${entered && issues.length ? " · needs attention" : ""}${setup ? " · setup needed" : ""}`;
  return { entered, issues, setup, status, value: index.measurements.get(key) };
}

export function coverageSummary(index: CoverageIndex): string {
  if (index.expected === 0) return "Add alternatives/criteria · 0 expected cells";
  return `${String(index.entered)}/${String(index.expected)} entered; ${String(index.missing)} missing; ${String(index.attention)} entered ${index.attention === 1 ? "cell needs" : "cells need"} attention`;
}

/** Clear absent references rather than selecting the item now at their former position. */
export function reconcileCoverageCell(index: CoverageIndex, cell: CoverageCell | null): CoverageCell | null {
  return cell && index.alternativePositions.has(cell.alternativeId) && index.leafPositions.has(cell.criterionId) ? cell : null;
}

export function coveragePage(total: number, requested: number) {
  const pages = Math.max(1, Math.ceil(total / COVERAGE_PAGE_SIZE));
  const page = Math.max(0, Math.min(pages - 1, requested));
  const start = page * COVERAGE_PAGE_SIZE;
  return { page, pages, start, end: Math.min(total, start + COVERAGE_PAGE_SIZE) };
}

export function pagesForCell(index: CoverageIndex, cell: CoverageCell | null) {
  return {
    row: Math.floor((cell ? index.alternativePositions.get(cell.alternativeId) ?? 0 : 0) / COVERAGE_PAGE_SIZE),
    column: Math.floor((cell ? index.leafPositions.get(cell.criterionId) ?? 0 : 0) / COVERAGE_PAGE_SIZE),
  };
}
