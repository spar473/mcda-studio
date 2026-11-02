import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { AnalysisConfiguration, Project, SensitivityProbe, SensitivityResult } from "../src/api/types";
import { VC_FILE, REPO, openTab, readJson, saveState, storedFile } from "./helpers";

const INFRA_FILE = resolve(REPO, "examples/infrastructure_procurement/project.json");
const CONFIG: AnalysisConfiguration = { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} };

async function engineSweep(page: Page, project: Project, node: string, configuration = CONFIG): Promise<SensitivityResult> {
  const r = await page.request.post("/api/sensitivity", { data: { project, node_id: node, configuration, steps: 101 } });
  expect(r.ok()).toBeTruthy();
  return await r.json() as SensitivityResult;
}
async function engineProbe(page: Page, project: Project, node: string, weight: number, configuration = CONFIG): Promise<SensitivityProbe> {
  const r = await page.request.post("/api/sensitivity/probe", { data: { project, node_id: node, weight, configuration } });
  expect(r.ok()).toBeTruthy();
  return await r.json() as SensitivityProbe;
}

const pick = (page: Page, node: string) => page.getByLabel("Criterion to vary").selectOption(node);
const cursor = (page: Page) => page.getByLabel("Hypothetical local weight");

async function readTable(page: Page): Promise<string[][]> {
  const rows = page.getByRole("table", { name: "Sensitivity values" }).locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  const out: string[][] = [];
  for (let i = 0; i < await rows.count(); i++) {
    out.push((await rows.nth(i).locator("th, td").allInnerTexts()).map((s) => s.trim()));
  }
  return out;
}

test("the VC sensitivity view reproduces the engine, crossovers included", async ({ page, request }, testInfo) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "b4-vc"; p.title = "B4 sensitivity";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);

  const sweep = await engineSweep(page, p, "team");
  expect(sweep.base_weight).toBeCloseTo(0.2941, 4);
  const winnerChange = sweep.first_winner_change_up;
  if (!winnerChange) throw new Error("the VC Team sweep must have a winner change");
  expect(winnerChange.weight).toBeCloseTo(0.569, 3);   // the documented threshold

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  await pick(page, "team");

  // Baseline: the probe must agree with the Results ranking exactly, to the digits shown.
  await expect(page.getByText(/baseline local weight/)).toContainText(sweep.base_weight.toFixed(4));
  const baseline = await engineProbe(page, p, "team", sweep.base_weight);
  expect(await readTable(page)).toEqual(baseline.alternatives.map((a) => [
    String(a.rank), a.name, a.value.toFixed(4), a.baseline_value.toFixed(4), String(a.baseline_rank), "—",
  ]));

  // Every exact crossover the engine found is offered, at full precision.
  for (const c of sweep.crossovers) {
    await expect(page.getByRole("button", { name: c.weight.toFixed(4) })).toBeVisible();
  }
  await expect(page.getByLabel("Stability intervals")).toContainText(winnerChange.weight.toFixed(4));

  // Probing the winner-change crossover: a tie, not a new unique winner.
  await page.getByRole("button", { name: winnerChange.weight.toFixed(4) }).click();
  await expect(cursor(page)).toHaveValue(String(winnerChange.weight));   // not snapped to the grid
  expect(sweep.grid).not.toContain(winnerChange.weight);
  const probed = await engineProbe(page, p, "team", winnerChange.weight);
  const shown = await readTable(page);
  expect(shown.map((r) => r[0])).toEqual(probed.alternatives.map((a) => String(a.rank)));
  expect(shown.map((r) => r[0])).toEqual(["1", "1", "3", "4"]);   // competition ranks, never 1,2,3,4
  expect(shown[0]?.[2]).toBe(shown[1]?.[2]);                       // the two leaders are tied
  await expect(page.getByText("TIED_ALTERNATIVES")).toBeVisible();
  await expect(page.getByText(/rank-one winner set differs from the baseline/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("b4-vc-crossover.png"), fullPage: true });

  // Exploring changed nothing at all.
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await request.delete(`/api/projects/${p.id}`);
});

test("sensitivity exploration never modifies the saved model", async ({ page, request }) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "b4-readonly"; p.title = "B4 read-only";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  const etag = (await request.get(`/api/projects/${p.id}`)).headers().etag;

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  for (const node of ["team", "market", "market_size"]) {
    await pick(page, node);
    await expect(page.getByTestId("sensitivity-chart")).toBeVisible();
    for (const w of ["0.1", "0.85", "0.5"]) {
      await cursor(page).fill(w);
      await cursor(page).press("Enter");
      await expect(page.getByRole("table", { name: "Sensitivity values" })).toBeVisible();
    }
    await page.locator(".sensitivity-chart").click({ position: { x: 300, y: 120 } });
  }
  // No edit, no undo entry, no revision change, no byte written.
  await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  expect((await request.get(`/api/projects/${p.id}`)).headers().etag).toBe(etag);

  // Reopening in a fresh page shows the original judgements untouched.
  await page.reload();
  await openTab(page, "Weights");
  await expect(page.getByLabel("Swing rating for Team", { exact: true })).toHaveValue("100");
  await request.delete(`/api/projects/${p.id}`);
});

test("sensitivity follows the selected profile and never shows one profile's curve under another", async ({ page, request }) => {
  const p = readJson(INFRA_FILE) as Project;
  p.id = "b4-profiles"; p.title = "B4 profile-aware sensitivity";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);

  const balanced = await engineSweep(page, p, "service");
  const consent = await engineSweep(page, p, "service", { ...CONFIG, weight_profile_id: "consent_led" });
  expect(balanced.base_weight).not.toBeCloseTo(consent.base_weight, 6);

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  await pick(page, "service");
  await expect(page.getByText(/baseline local weight/)).toContainText(balanced.base_weight.toFixed(4));
  await expect(page.getByLabel("Sensitivity context")).toContainText("Balanced");

  // Switch profile: the baseline, the context label and the numbers all move together.
  await page.getByLabel("Weight profile", { exact: true }).selectOption("consent_led");
  await expect(page.getByLabel("Sensitivity context")).toContainText("Consent led");
  await expect(page.getByText(/baseline local weight/)).toContainText(consent.base_weight.toFixed(4));
  const probed = await engineProbe(page, p, "service", consent.base_weight, { ...CONFIG, weight_profile_id: "consent_led" });
  expect((await readTable(page)).map((r) => r[2])).toEqual(probed.alternatives.map((a) => a.value.toFixed(4)));

  // A deeper branch and an only child behave as the engine says.
  await pick(page, "capacity_margin");
  await expect(page.getByTestId("sensitivity-chart")).toBeVisible();
  const trackRecord = page.getByLabel("Criterion to vary").locator("option", { hasText: "Contractor track record" });
  await expect(trackRecord).toHaveAttribute("disabled", "");
  await expect(trackRecord).toContainText("cannot vary");
  await expect(saveState(page)).toHaveText("All changes saved");
  await request.delete(`/api/projects/${p.id}`);
});

test("a late response for an abandoned context cannot overwrite the current one", async ({ page, request }) => {
  const p = readJson(INFRA_FILE) as Project;
  p.id = "b4-stale"; p.title = "B4 stale sensitivity";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const first = await engineSweep(page, p, "lifecycle_cost");
  const second = await engineSweep(page, p, "consent");
  expect(first.base_weight).not.toBeCloseTo(second.base_weight, 6);

  // Hold the first sweep open, switch criterion, then release the obsolete response.
  let release = (): void => undefined;
  const held = new Promise<void>((r) => { release = () => { r(); }; });
  let seen = 0;
  await page.route("**/api/sensitivity", async (route) => {
    if (++seen === 1) await held;
    await route.continue();
  });

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  await pick(page, "lifecycle_cost");
  await pick(page, "consent");
  release();
  await page.waitForLoadState("networkidle");

  await expect(page.getByText(/baseline local weight/)).toContainText(second.base_weight.toFixed(4));
  await expect(page.getByText(/baseline local weight/)).not.toContainText(first.base_weight.toFixed(4));
  await expect(page.locator(".selected-weight-path")).toContainText("Consent and community");
  await expect(saveState(page)).toHaveText("All changes saved");
  await request.delete(`/api/projects/${p.id}`);
});

test("hiding an alternative changes the chart only, and the view works on a narrow window", async ({ page, request }, testInfo) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "b4-narrow"; p.title = "B4 narrow sensitivity";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.setViewportSize({ width: 760, height: 1000 });
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Sensitivity");
  await pick(page, "team");

  const rowsBefore = await readTable(page);
  await expect(page.getByTestId("series-hyades")).toBeVisible();
  await page.getByRole("checkbox", { name: /Hyades/ }).uncheck();
  await expect(page.getByTestId("series-hyades")).toHaveCount(0);
  await expect(page.getByText(/1 alternative\(s\) hidden/)).toBeVisible();
  // The numbers are unchanged: hiding a line is not a model change.
  expect(await readTable(page)).toEqual(rowsBefore);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("b4-narrow-layout.png"), fullPage: true });
  await expect(saveState(page)).toHaveText("All changes saved");
  await request.delete(`/api/projects/${p.id}`);
});
