import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { ProjectDocument, ScreeningWhatIf } from "../src/api/types";
import { openTab, saveState, storedFile } from "./helpers";
const id = "nz_venture_screening_study";
async function gallery(page: Page) {
  await page.goto("/"); await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click();
  await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
}
async function snapshot(request: APIRequestContext) {
  const response = await request.get(`/api/projects/${id}`);
  return { body: await response.json() as ProjectDocument, etag: response.headers().etag, file: await storedFile(request, id) };
}
async function unchanged(page: Page, request: APIRequestContext, before: Awaited<ReturnType<typeof snapshot>>) {
  const after = await snapshot(request); expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
  await expect(saveState(page)).toHaveText("All changes saved"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
}
// A ratings map has no meaningful key order: compare exact keys and full-precision values.
const entries = (ratings: Record<string, number>) => JSON.stringify(Object.entries(ratings).sort(([left], [right]) => left < right ? -1 : 1));
function response(page: Page, ratings: Record<string, number>) {
  return page.waitForResponse(value => value.url().endsWith("/api/screening-summary/what-if") && value.request().method() === "POST" &&
    entries((value.request().postDataJSON() as { ratings: Record<string, number> }).ratings) === entries(ratings));
}
async function openTrial(page: Page) {
  const received = response(page, {}); await page.getByText("What-if weights", { exact: true }).click();
  const baseline = await (await received).json() as ScreeningWhatIf;
  await expect(page.getByRole("slider", { name: "What-if Team", exact: true })).toBeVisible(); return baseline;
}
async function download(page: Page, name: string) {
  const pending = page.waitForEvent("download"); await page.getByRole("button", { name, exact: true }).click();
  const path = await (await pending).path(); if (!path) throw Error("Download missing"); return readFileSync(path);
}
async function exactRating(page: Page, name: string, rating: string) {
  const disclosure = page.getByText(`Enter an exact raw rating for ${name}`, { exact: true });
  if (await disclosure.evaluate(element => !(element.parentElement as HTMLDetailsElement).open)) await disclosure.click();
  const input = page.getByLabel(`Exact raw rating for ${name}`, { exact: true }); await input.fill(rating); await input.press("Tab");
}

test("a trial changes only the Results summary and ranking chart, blocks other controls, and Reset restores exact saved downloads", async ({ page, request }) => {
  test.setTimeout(120_000); await gallery(page);
  await openTab(page, "Evidence"); await page.getByRole("button", { name: "Open the study's evidence", exact: true }).click();
  await expect(page.getByLabel("Evidence claims", { exact: true })).toBeVisible(); await openTab(page, "Results");
  const summary = page.getByRole("table", { name: "Screening summary", exact: true });
  await expect(summary.locator("tbody tr")).toHaveCount(8);
  const savedRows = await summary.locator("tbody tr").allTextContents(), ranking = await page.getByRole("table", { name: "Ranking", exact: true }).allTextContents();
  const segments = await page.locator(".results-chart rect[data-contribution]").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-contribution")));
  const before = await snapshot(request), savedJSON = await download(page, "Download analysis JSON"), savedCSV = await download(page, "Download CSV");
  const writes: string[] = [], trialBodies: unknown[] = [], otherProjects: unknown[] = [];
  page.on("request", value => {
    if (value.url().endsWith("/api/edit") || ["PUT", "DELETE"].includes(value.method()) && value.url().includes(`/api/projects/${id}`)) writes.push(value.url());
    if (value.url().endsWith("/api/screening-summary/what-if")) trialBodies.push(value.postDataJSON());
    else if (value.method() === "POST" && /\/api\/(analysis|screening|sensitivity|comparison)/.test(value.url())) {
      const body = value.postDataJSON() as { project?: unknown }; if (body.project) otherProjects.push(body.project);
    }
  });
  await page.getByRole("checkbox", { name: "Compare profiles", exact: true }).check();
  await expect(page.getByRole("table", { name: "Profile rankings and movements", exact: true }).locator("tbody tr")).toHaveCount(8);
  const baseline = await openTrial(page); expect(baseline.controls.map(control => control.criterion_id)).toEqual(["team", "problem_solution", "market", "traction"]);
  const received = response(page, { team: 0 }); await page.getByRole("slider", { name: "What-if Team", exact: true }).focus(); await page.keyboard.press("Home");
  const trial = await (await received).json() as ScreeningWhatIf; expect(trial.status).toBe("available");
  if (!trial.record || !trial.summary) throw Error("Trial result missing");
  await expect(page.getByText("Open-question counts reflect the saved weights", { exact: true })).toBeVisible();
  await expect(summary.getByRole("columnheader", { name: "Open questions", exact: true })).toHaveCount(0);
  expect(await summary.locator("tbody tr").locator("th").allTextContents()).toEqual(trial.summary.rows.map(row => row.name));
  expect(await summary.locator("tbody tr").evaluateAll(rows => rows.map(row => row.querySelectorAll("td")[1]?.textContent))).toEqual(trial.summary.rows.map(row => row.value.toFixed(4)));
  const chart = page.getByRole("group", { name: "Overall MAVT values", exact: true });
  expect(await chart.locator("g[data-alternative-id]").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-alternative-id")))).toEqual(trial.record.result.ranking.map(row => row.alternative_id));
  expect(await page.getByRole("table", { name: "Ranking", exact: true }).allTextContents()).toEqual(ranking);
  expect(await page.locator(".results-chart rect[data-contribution]").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-contribution")))).toEqual(segments);
  await expect(summary.getByRole("button", { name: "Upstock", exact: true })).toBeDisabled(); await summary.locator("tbody tr").first().click(); await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Profile comparison", exact: true })).toHaveCount(0); await expect(page.getByText("Compare profiles: Reset what-if to use this", { exact: true })).toBeVisible();
  for (const button of await page.getByRole("button", { name: /^Download / }).all()) if (await button.isVisible()) await expect(button).toBeDisabled();
  await openTab(page, "Sensitivity"); await expect(page.getByText("Reset what-if to use this", { exact: true })).toBeVisible(); await expect(page.locator(".selected-weight-path")).toHaveCount(0);
  await openTab(page, "Compare"); await expect(page.getByRole("table", { name: "Methods side by side", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download comparison JSON", exact: true })).toBeDisabled(); await expect(page.getByRole("button", { name: "Download comparison CSV", exact: true })).toBeDisabled();
  await openTab(page, "Results"); await expect(page.getByRole("button", { name: "Reset", exact: true })).toBeEnabled(); await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(summary.getByRole("columnheader", { name: "Open questions", exact: true })).toBeVisible(); expect(await summary.locator("tbody tr").allTextContents()).toEqual(savedRows);
  expect((await download(page, "Download analysis JSON")).equals(savedJSON)).toBe(true); expect((await download(page, "Download CSV")).equals(savedCSV)).toBe(true);
  expect(trialBodies.length).toBeGreaterThan(1);
  for (const body of trialBodies) { expect((body as { project: unknown }).project).toEqual(before.body.project); expect(body).not.toHaveProperty("dossier"); }
  for (const source of otherProjects) expect(source).toEqual(before.body.project);
  expect(writes).toEqual([]); await expect(page.getByRole("button", { name: /save.*profile/i })).toHaveCount(0); await unchanged(page, request, before);
});

test("exact uncapped ratings remain full precision, all-zero trials are unavailable, and profile/scenario changes clear trials", async ({ page, request }) => {
  test.setTimeout(120_000); await gallery(page); const before = await snapshot(request); await openTrial(page);
  let received = response(page, { team: 137.12345678901235 }); await exactRating(page, "Team", "137.12345678901235");
  const precise = await (await received).json() as ScreeningWhatIf;
  expect(precise.ratings).toEqual({ team: 137.12345678901235 }); expect(precise.controls.find(control => control.criterion_id === "team")?.raw_rating).toBe(137.12345678901235);
  received = response(page, {}); await page.getByLabel("Weight profile", { exact: true }).selectOption("commercial_traction"); await received;
  await expect(page.getByRole("button", { name: "Reset", exact: true })).toBeDisabled(); await expect(page.getByRole("columnheader", { name: "Open questions", exact: true })).toBeVisible();
  const zero: Record<string, number> = {};
  for (const [key, name] of [["team", "Team"], ["problem_solution", "Problem and solution"], ["market", "Market"], ["traction", "Traction"]]) {
    if (!key || !name) throw Error("Control missing"); zero[key] = 0;
    received = response(page, { ...zero }); await exactRating(page, name, "0"); await received;
  }
  await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toHaveCount(0); await expect(page.getByRole("group", { name: "Overall MAVT values", exact: true })).toHaveCount(0);
  await expect(page.getByText("Open-question counts reflect the saved weights", { exact: true })).toBeVisible();
  received = response(page, {}); await page.getByLabel("Scenario", { exact: true }).selectOption("linear_market_size"); await received;
  await expect(page.getByRole("button", { name: "Reset", exact: true })).toBeDisabled(); await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
  await unchanged(page, request, before);
});
