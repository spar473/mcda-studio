import { expect, test, type APIRequestContext, type Download, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { AnalysisExportDocument, Project, MavtResult } from "../src/api/types";
import { VC_FILE, REPO, openTab, readJson, saveState, storedFile } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? "python3";
const ranking = (page: Page) => page.getByRole("table", { name: "Ranking", exact: true });
const overall = (page: Page) => page.getByRole("group", { name: "Overall MAVT values", exact: true });
const contributions = (page: Page) => page.getByRole("group", { name: "Weighted leaf contributions", exact: true });
async function load(page: Page, request: APIRequestContext, id: string, file = VC_FILE) {
  const p = readJson(file) as Project; p.id = id;
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${id}`); await openTab(page, "Results"); await expect(ranking(page)).toBeVisible(); return p;
}
async function jsonDownload(page: Page, info: TestInfo, name = "analysis.json"): Promise<AnalysisExportDocument> {
  const event = page.waitForEvent("download"); await page.getByRole("button", { name: "Download analysis JSON", exact: true }).click();
  const download = await event; const path = info.outputPath(name); await download.saveAs(path);
  return JSON.parse(readFileSync(path, "utf8")) as AnalysisExportDocument;
}
async function csvDownload(page: Page, info: TestInfo, table: string) {
  await page.getByLabel("CSV table", { exact: true }).selectOption(table);
  const event = page.waitForEvent("download"); await page.getByRole("button", { name: "Download CSV", exact: true }).click();
  const file = await event; const path = info.outputPath(`${table}.csv`); await file.saveAs(path);
  return JSON.parse(execFileSync(PYTHON, ["-c", "import csv,json,sys\nwith open(sys.argv[1],newline='',encoding='utf-8') as f:\n print(json.dumps(list(csv.DictReader(f))))", path], { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 })) as Record<string, string>[];
}
function cli(document: AnalysisExportDocument, info: TestInfo): MavtResult {
  const path = info.outputPath("reproduced-source.json"); writeFileSync(path, JSON.stringify(document.source_project));
  const cfg = document.record.result.configuration;
  return JSON.parse(execFileSync(PYTHON, ["-m", "mcda_studio", "evaluate", path, "--json",
    ...(cfg.scenario_id ? ["--scenario", cfg.scenario_id] : []), ...(cfg.weight_profile_id ? ["--profile", cfg.weight_profile_id] : [])], { cwd: REPO, encoding: "utf8" })) as MavtResult;
}

test("VC linked bars, eight contributions, heatmap, dominance and full-precision exports preserve the project", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-vc"); const before = await storedFile(request, p.id);
  await expect(overall(page).locator("g[data-alternative-id]")).toHaveCount(4);
  await expect(contributions(page).locator("rect[data-contribution]")).toHaveCount(32);
  await expect(ranking(page)).toContainText("0.7227");
  await page.getByRole("button", { name: "Inspect alternative Forever Harvest (forever_harvest), rank 1, value 0.7226678550207962", exact: true }).click();
  await page.getByLabel("Criterion to inspect", { exact: true }).selectOption("market_size");
  await expect(page.getByRole("region", { name: "Selected criterion and alternative" })).toContainText("1.38 US$ bn");
  await expect(page.getByRole("region", { name: "Selected criterion and alternative" })).toContainText("control_points");
  const heatmap = page.getByRole("table", { name: "Partial-value heatmap", exact: true });
  await expect(heatmap.locator("tbody button.heatmap-cell")).toHaveCount(32);
  await expect(heatmap).toContainText("Raw: 26.45 US$ bn");
  await overall(page).scrollIntoViewIfNeeded(); await page.screenshot({ path: info.outputPath("b6-vc-ranking.png"), fullPage: true });
  await contributions(page).scrollIntoViewIfNeeded(); await page.screenshot({ path: info.outputPath("b6-vc-contributions.png"), fullPage: true });
  await heatmap.getByRole("button", { name: "Market Size", exact: true }).scrollIntoViewIfNeeded(); await page.screenshot({ path: info.outputPath("b6-vc-heatmap.png"), fullPage: true });
  const matrix = page.getByRole("table", { name: "Dominance matrix", exact: true });
  await matrix.getByRole("button", { name: /Forever Harvest versus Outlier Space:/ }).click();
  await expect(page.getByRole("table", { name: "Dominance supporting partial values", exact: true }).locator("tbody tr")).toHaveCount(8);
  const document = await jsonDownload(page, info, "b6-vc-analysis.json");
  expect(document.record.result).toEqual(cli(document, info));
  const rankingRows = await csvDownload(page, info, "ranking");
  expect(rankingRows.map(row => Number(row.overall_value))).toEqual(document.record.result.ranking.map(a => a.value));
  const contributionRows = await csvDownload(page, info, "contributions"); expect(contributionRows).toHaveLength(32);
  for (const row of contributionRows) {
    const detail = document.record.result.alternatives.find(a => a.alternative_id === row.alternative_id);
    expect(Number(row.weighted_contribution)).toBe(detail?.weighted_contributions[row.criterion_id ?? ""]);
    expect(row.record_digest).toBe(document.record.record_digest);
  }
  const partialRows = await csvDownload(page, info, "partial_values"); expect(partialRows).toHaveLength(32);
  const dominanceRows = await csvDownload(page, info, "dominance"); expect(dominanceRows).toHaveLength(16);
  expect((await storedFile(request, p.id)).equals(before)).toBe(true); await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled(); await request.delete(`/api/projects/${p.id}`);
});

test("linear Market Size comparison, hidden-series SVG and CSV retain original totals and profile contexts", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-scenario"); const before = await storedFile(request, p.id);
  await page.getByLabel("Scenario", { exact: true }).selectOption("linear_market_size");
  await expect(ranking(page).locator("tbody tr").nth(2)).toContainText("Hyades");
  await expect(page.getByRole("table", { name: "Results scenario comparison", exact: true })).toContainText("0.5561");
  await page.getByText("Chart visibility and accessible criterion legend", { exact: true }).click();
  await page.getByLabel("Show criterion Market Size", { exact: true }).uncheck(); await page.getByLabel("Show alternative Hyades", { exact: true }).uncheck();
  await expect(page.getByTestId("contribution-total-kura_dynamics")).toHaveText("0.5561");
  await expect(page.getByLabel("Chart visibility summary")).toContainText("market_size");
  const svgEvent = page.waitForEvent("download"); await page.getByRole("button", { name: "Download contributions SVG", exact: true }).click();
  const svg = await svgEvent; const path = info.outputPath("b6-filtered-contributions.svg"); await svg.saveAs(path);
  const xml = readFileSync(path, "utf8"); expect(xml).toContain("Hidden criteria: market_size"); expect(xml).toContain("Hidden alternatives: hyades"); expect(xml).toContain("preference value");
  execFileSync(PYTHON, ["-c", "import sys,xml.etree.ElementTree as ET\nET.parse(sys.argv[1])", path]);
  const document = await jsonDownload(page, info, "b6-scenario-analysis.json"); expect(document.record.result).toEqual(cli(document, info));
  expect(document.presentation.hidden_criterion_ids).toEqual(["market_size"]);
  const rows = await csvDownload(page, info, "comparison"); expect(rows).toHaveLength(4);
  expect(rows.find(row => row.alternative_id === "kura_dynamics")).toMatchObject({ base_rank: "3", scenario_rank: "4", base_profile_id: "default", scenario_profile_id: "default" });
  expect(rows.find(row => row.alternative_id === "hyades")).toMatchObject({ base_rank: "4", scenario_rank: "3" });
  await page.getByRole("group", { name: "Base versus selected scenario", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("b6-vc-comparison.png"), fullPage: true });
  expect((await storedFile(request, p.id)).equals(before)).toBe(true); await request.delete(`/api/projects/${p.id}`);
});

test("infrastructure exports reproduce the independent oracle under scenario and explicit profile; reopen is unchanged", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-infrastructure", resolve(REPO, "examples/infrastructure_procurement/project.json")); const before = await storedFile(request, p.id);
  await page.getByLabel("Scenario", { exact: true }).selectOption("consent_review");
  await expect(page.getByLabel("Results analysis context")).toContainText("Consent led");
  const document = await jsonDownload(page, info, "b6-infrastructure-analysis.json"); expect(document.record.result).toEqual(cli(document, info));
  const expected = JSON.parse(execFileSync(PYTHON, ["-c", "import runpy,json\nm=runpy.run_path('tests/regression/test_infrastructure_procurement.py')\nprint(json.dumps(m['oracle_values'](m['ratings']('consent_led'),outage='linear')))"] , { cwd: REPO, encoding: "utf8" })) as Record<string, number>;
  for (const alt of document.record.result.ranking) expect(alt.value).toBeCloseTo(expected[alt.alternative_id] ?? -1, 12);
  expect(document.record.criteria.find(c => c.criterion_id === "outage_hours")?.path_ids).toHaveLength(3);
  expect(document.record.comparison?.baseline.weight_profile_id).toBe("default"); expect(document.record.result.weight_profile_id).toBe("consent_led");
  await page.getByLabel("Criterion to inspect", { exact: true }).selectOption("community");
  await page.getByLabel("Alternative to inspect", { exact: true }).selectOption("alliance");
  await page.getByRole("table", { name: "Partial-value heatmap", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("b6-infrastructure-heatmap.png"), fullPage: true });
  await page.getByLabel("Weight profile", { exact: true }).selectOption("default");
  await expect(page.getByLabel("Results analysis context")).toContainText("Balanced");
  await expect(page.getByRole("table", { name: "Results scenario comparison", exact: true })).toBeVisible();
  const explicit = await jsonDownload(page, info, "b6-infrastructure-explicit.json"); expect(explicit.record.result).toEqual(cli(explicit, info));
  expect(explicit.record.comparison?.baseline.weight_profile_id).toBe(explicit.record.result.weight_profile_id);
  await page.reload(); await openTab(page, "Results"); await expect(ranking(page)).toBeVisible();
  expect((await storedFile(request, p.id)).equals(before)).toBe(true); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled(); await request.delete(`/api/projects/${p.id}`);
});

test("late scenario records and late export responses cannot appear under a newer context", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-stale"); const downloads: Download[] = []; page.on("download", download => { downloads.push(download); });
  let releaseRecord: () => void = () => undefined, releaseExport: () => void = () => undefined;
  const heldRecord = new Promise<void>(r => { releaseRecord = r; }), heldExport = new Promise<void>(r => { releaseExport = r; }); let recordStarted = false, exportStarted = false;
  await page.route("**/api/analysis/record", async route => {
    const body = route.request().postDataJSON() as { configuration: { scenario_id: string | null } };
    if (body.configuration.scenario_id === "linear_market_size") { recordStarted = true; const response = await route.fetch(); await heldRecord; await route.fulfill({ response }); } else await route.continue();
  });
  await page.getByLabel("Scenario", { exact: true }).selectOption("linear_market_size"); await expect.poll(() => recordStarted).toBe(true);
  await page.getByLabel("Scenario", { exact: true }).selectOption(""); await expect(ranking(page)).toContainText("0.5986"); releaseRecord(); await page.waitForLoadState("networkidle"); await expect(ranking(page)).not.toContainText("0.5561");
  await page.unroute("**/api/analysis/record");
  await page.route("**/api/analysis/export", async route => { const response = await route.fetch(); exportStarted = true; await heldExport; await route.fulfill({ response }); });
  await page.getByRole("button", { name: "Download analysis JSON", exact: true }).click(); await expect.poll(() => exportStarted).toBe(true);
  await page.getByLabel("Scenario", { exact: true }).selectOption("linear_market_size"); await expect(ranking(page)).toContainText("0.5561"); releaseExport(); await page.waitForLoadState("networkidle"); expect(downloads).toHaveLength(0);
  await page.unroute("**/api/analysis/export"); const document = await jsonDownload(page, info, "b6-after-context-switch.json"); expect(document.record.result.scenario_id).toBe("linear_market_size"); await request.delete(`/api/projects/${p.id}`);
});

test("tied scores, duplicate names, one alternative, zero values and invalid states remain explicit", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-ties", resolve(REPO, "tests/fixtures/tied_project.json"));
  await expect(ranking(page).locator("tbody tr").nth(0).locator("td").first()).toHaveText("1"); await expect(ranking(page).locator("tbody tr").nth(1).locator("td").first()).toHaveText("1"); await expect(ranking(page).locator("tbody tr").nth(2).locator("td").first()).toHaveText("3");
  await page.getByRole("table", { name: "Dominance matrix", exact: true }).getByRole("button", { name: "Equal name versus Third option: Dominates", exact: true }).first().click();
  await expect(page.getByRole("table", { name: "Dominance supporting partial values", exact: true })).toBeVisible();
  await page.getByRole("table", { name: "Dominance matrix", exact: true }).scrollIntoViewIfNeeded(); await page.screenshot({ path: info.outputPath("b6-ties-dominance.png"), fullPage: true });
  const single = structuredClone(p); single.id = "b6-one"; single.alternatives = single.alternatives.slice(0, 1); single.performances = single.performances.filter(m => m.alternative_id === single.alternatives[0]?.id).map(m => ({ ...m, value: 0 }));
  expect((await request.post("/api/projects/import", { data: single })).status()).toBe(201); await page.goto(`/#/p/${single.id}`); await openTab(page, "Results"); await expect(ranking(page).locator("tbody tr")).toHaveCount(1); await expect(ranking(page)).toContainText("0.0000");
  const invalid = structuredClone(p); invalid.id = "b6-incomplete"; invalid.performances.pop(); expect((await request.post("/api/projects/import", { data: invalid })).status()).toBe(201);
  await page.goto(`/#/p/${invalid.id}`); await openTab(page, "Results"); await expect(page.getByText(/validation error\(s\)/)).toBeVisible(); await expect(page.getByRole("button", { name: "Download analysis JSON", exact: true })).toHaveCount(0);
  for (const id of [p.id, single.id, invalid.id]) await request.delete(`/api/projects/${id}`);
});

test("CSV formula-like names and control characters are safely encoded while JSON retains originals", async ({ page, request }, info) => {
  const p = readJson(resolve(REPO, "tests/fixtures/tied_project.json")) as Project; p.id = "b6-csv-safety";
  const alt = p.alternatives[0], criterion = p.criteria[0]; if (!alt || !criterion) throw Error("fixture missing cell");
  alt.name = " \t＝HYPERLINK(\"https://invalid.test\")"; criterion.name = "\r\n@formula";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201); await page.goto(`/#/p/${p.id}`); await openTab(page, "Results"); await expect(ranking(page)).toBeVisible();
  const document = await jsonDownload(page, info); expect(document.source_project.alternatives[0]?.name).toBe(alt.name);
  const rows = await csvDownload(page, info, "partial_values"); const row = rows.find(r => r.alternative_id === alt.id && r.criterion_id === criterion.id);
  expect(row?.alternative_name).toMatch(/^TEXT:/); expect(row?.criterion_name).toMatch(/^TEXT:/); const encoded = row?.alternative_name ?? "";
  for (let i = 0; i < encoded.length; i++) expect(encoded.charCodeAt(i)).toBeGreaterThanOrEqual(32);
  await request.delete(`/api/projects/${p.id}`);
});

test("larger generic model renders complete data, avoids re-evaluation on selection and exports within bounds", async ({ page, request }, info) => {
  test.setTimeout(60_000); let evaluations = 0; page.on("request", r => { if (r.url().endsWith("/api/analysis/record")) evaluations++; });
  const started = Date.now(); const p = await load(page, request, "b6-performance", resolve(REPO, "tests/fixtures/performance_project.json"));
  await expect(overall(page).locator("g[data-alternative-id]")).toHaveCount(50); await expect(contributions(page).locator("rect[data-contribution]")).toHaveCount(2000);
  await expect(page.getByRole("table", { name: "Partial-value heatmap", exact: true }).locator("button.heatmap-cell")).toHaveCount(2000);
  const renderMs = Date.now() - started; expect(renderMs).toBeLessThan(20_000);
  await page.getByLabel("Criterion to inspect", { exact: true }).selectOption("metric_0_0_0"); await page.getByLabel("Alternative to inspect", { exact: true }).selectOption("option_010");
  await page.getByLabel("Results order", { exact: true }).selectOption("project"); await page.waitForLoadState("networkidle"); expect(evaluations).toBe(1);
  const exportStarted = Date.now(); const rows = await csvDownload(page, info, "contributions"); const exportMs = Date.now() - exportStarted; expect(rows).toHaveLength(2000);
  writeFileSync(info.outputPath("b6-browser-performance.json"), JSON.stringify({ alternatives: 50, leaves: 40, render_to_complete_workspace_ms: renderMs, contribution_csv_download_and_parse_ms: exportMs, record_requests_after_exploration: evaluations }, null, 2));
  await expect(saveState(page)).toHaveText("All changes saved"); await request.delete(`/api/projects/${p.id}`);
});

test("narrow panes and zoom retain keyboard tables and explicit chart overflow", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-narrow"); await page.setViewportSize({ width: 700, height: 980 });
  await page.evaluate(() => { document.documentElement.style.zoom = "1.25"; });
  await page.emulateMedia({ colorScheme: "dark" });
  const heatmap = page.getByRole("table", { name: "Partial-value heatmap", exact: true });
  const first = heatmap.locator("button.heatmap-cell").first(); await first.focus(); await page.keyboard.press("ArrowRight"); await expect(heatmap.locator("button.heatmap-cell").nth(1)).toBeFocused();
  await page.getByRole("region", { name: "Overall MAVT values scroll area", exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("b6-narrow-zoom.png"), fullPage: true }); await request.delete(`/api/projects/${p.id}`);
});

test("rapid explicit profile switching keeps all result views and downloads on the latest profile", async ({ page, request }, info) => {
  const p = await load(page, request, "b6-profile-stale", resolve(REPO, "examples/infrastructure_procurement/project.json"));
  let release: () => void = () => undefined; const held = new Promise<void>(r => { release = r; }); let started = false;
  await page.route("**/api/analysis/record", async route => {
    const body = route.request().postDataJSON() as { configuration: { weight_profile_id: string | null } };
    if (body.configuration.weight_profile_id === "consent_led") { const response = await route.fetch(); started = true; await held; await route.fulfill({ response }); } else await route.continue();
  });
  await page.getByLabel("Weight profile", { exact: true }).selectOption("consent_led"); await expect.poll(() => started).toBe(true);
  await page.getByLabel("Weight profile", { exact: true }).selectOption("default"); await expect(page.getByLabel("Results analysis context")).toContainText("Resolved profile: Balanced");
  release(); await page.waitForLoadState("networkidle"); await expect(page.getByLabel("Results analysis context")).toContainText("Resolved profile: Balanced");
  const document = await jsonDownload(page, info, "b6-latest-profile.json"); expect(document.record.result.weight_profile_id).toBe("default"); expect(document.record.result).toEqual(cli(document, info));
  await request.delete(`/api/projects/${p.id}`);
});
