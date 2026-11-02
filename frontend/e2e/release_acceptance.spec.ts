import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Project, SensitivityResult } from "../src/api/types";
import { VC_FILE, REPO, openTab, readJson, saveState, storedFile } from "./helpers";

test("B7 all reference crossover probes retain exact weights, tied winners and unchanged saved data", async ({ page, request }, info) => {
  const p = readJson(VC_FILE) as Project; p.id = "b7-crossovers";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  const evidence = [];
  for (const [node, reference] of [["team", .5688552162065278], ["market", .6736973263477098], ["market_size", .8727820972886765]] as const) {
    const response = page.waitForResponse(r => r.url().endsWith("/api/sensitivity") && (r.request().postDataJSON() as { node_id: string }).node_id === node);
    await page.getByLabel("Criterion to vary").selectOption(node);
    const sweep = await (await response).json() as SensitivityResult;
    const crossing = sweep.first_winner_change_up; if (!crossing) throw Error("Missing reference crossover");
    expect(crossing.weight).toBeCloseTo(reference, 12);
    await page.getByRole("button", { name: crossing.weight.toFixed(4), exact: true }).click();
    await expect(page.getByLabel("Hypothetical local weight")).toHaveValue(String(crossing.weight));
    await expect(page.getByText("TIED_ALTERNATIVES", { exact: true })).toBeVisible();
    await expect(page.getByText(/rank-one winner set differs from the baseline/)).toBeVisible();
    const ranks = await page.getByRole("table", { name: "Sensitivity values", exact: true }).locator("tbody tr td:first-child").allTextContents();
    expect(ranks.map(s => s.trim())).toEqual(["1", "1", "3", "4"]);
    evidence.push({ node, exact_weight: crossing.weight, ranks });
  }
  await page.screenshot({ path: info.outputPath("b7-reference-exact-crossover.png") });
  writeFileSync(info.outputPath("b7-reference-crossover-evidence.json"), JSON.stringify(evidence, null, 2));
  await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
});

test("B7 transport errors hide analytics, preserve unsaved edits and recover through supported controls", async ({ page, request }, info) => {
  const p = readJson(VC_FILE) as Project; p.id = "b7-network";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  await page.route("**/api/analysis/record", r => r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "AUDIT_UNAVAILABLE", message: "Temporary analysis outage", details: [] } }) }));
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Results");
  await expect(page.getByRole("alert").filter({ hasText: "Temporary analysis outage" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download analysis JSON", exact: true })).toHaveCount(0);
  await page.unroute("**/api/analysis/record"); await openTab(page, "Weights"); await openTab(page, "Results");
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toContainText("0.7227");
  await openTab(page, "Alternatives");
  await page.route("**/api/edit", r => r.abort("failed"));
  const name = page.getByLabel("Name of alternative Hyades", { exact: true });
  await name.fill("Hyades reviewed"); await name.press("Enter");
  await expect(page.getByRole("alert")).toBeVisible();
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await page.unroute("**/api/edit"); await name.fill("Hyades reviewed"); await name.press("Enter");
  await expect(page.getByLabel("Name of alternative Hyades reviewed", { exact: true })).toBeVisible();
  await page.route(`**/api/projects/${p.id}`, r => r.request().method() === "PUT" ? r.abort("failed") : r.continue());
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Not saved" })).toBeVisible();
  await expect(saveState(page)).toHaveText("● Unsaved changes");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await page.screenshot({ path: info.outputPath("b7-recoverable-save-error.png") });
  await page.unroute(`**/api/projects/${p.id}`); await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved"); await page.reload(); await openTab(page, "Alternatives");
  await expect(page.getByLabel("Name of alternative Hyades reviewed", { exact: true })).toBeVisible();
});

test("B7 larger-model loading, tree, weights, sensitivity, scenarios and exports are measured", async ({ page, request }, info) => {
  test.setTimeout(90_000);
  const p = readJson(resolve(REPO, "tests/fixtures/performance_project.json")) as Project; p.id = "b7-performance";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id); const metrics: Record<string, number> = {};
  let start = Date.now(); await page.goto(`/#/p/${p.id}`);
  await expect(page.getByRole("treeitem")).toHaveCount(52); metrics.load_and_tree_ms = Date.now() - start;
  start = Date.now(); await openTab(page, "Weights"); await expect(page.getByLabel("Swing rating for Performance objective 0", { exact: true })).toHaveValue("100");
  await expect(page.getByRole("table", { name: "Swing ratings under top level", exact: true })).toContainText("0.3571"); metrics.weights_ms = Date.now() - start;
  start = Date.now(); await openTab(page, "Results"); await expect(page.getByRole("table", { name: "Ranking", exact: true }).locator("tbody tr")).toHaveCount(50);
  await expect(page.getByRole("table", { name: "Partial-value heatmap", exact: true }).locator("button.heatmap-cell")).toHaveCount(2000); metrics.record_and_charts_ms = Date.now() - start;
  start = Date.now(); await openTab(page, "Sensitivity"); await page.getByLabel("Criterion to vary").selectOption("objective_0");
  await expect(page.getByRole("table", { name: "Sensitivity values", exact: true }).locator("tbody tr")).toHaveCount(50); metrics.sensitivity_and_probe_ms = Date.now() - start;
  start = Date.now(); await openTab(page, "Results"); await page.getByLabel("Scenario", { exact: true }).selectOption("different_profile");
  await expect(page.getByLabel("Results analysis context")).toContainText("Alternative benchmark preferences");
  await expect(page.getByRole("table", { name: "Results scenario comparison", exact: true }).locator("tbody tr")).toHaveCount(50); metrics.scenario_switch_ms = Date.now() - start;
  start = Date.now(); const download = page.waitForEvent("download"); await page.getByRole("button", { name: "Download analysis JSON", exact: true }).click();
  const path = info.outputPath("b7-performance-analysis.json"); await (await download).saveAs(path); metrics.json_download_ms = Date.now() - start; metrics.json_bytes = readFileSync(path).byteLength;
  await page.getByRole("button", { name: "Overall values", exact: true }).click(); await page.screenshot({ path: info.outputPath("b7-larger-model.png") });
  writeFileSync(info.outputPath("b7-browser-performance.json"), JSON.stringify({ fixture: { alternatives: 50, leaves: 40, nodes: 52, measurements: 2000, depth: 3 }, metrics }, null, 2));
  expect((await storedFile(request, p.id)).equals(before)).toBe(true); await expect(saveState(page)).toHaveText("All changes saved");
});
