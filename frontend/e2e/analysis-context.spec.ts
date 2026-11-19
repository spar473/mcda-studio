import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import type { Project, MavtResult } from "../src/api/types";
import { at, VC_FILE, REPO, openTab, readJson, saveState, selectNode, storedFile } from "./helpers";

test("one context survives tabs and explicitly overrides saved scenario defaults without saving", async ({ page, request }) => {
  const p = readJson(resolve(REPO, "examples/supplier_selection/project.json")) as Project;
  p.id = "context-browser"; p.title = "Context test model";
  p.analysis.scenario_id = "linear_defects";
  const imported = await request.post("/api/projects/import", { data: p }); expect(imported.status()).toBe(201);
  const before = await storedFile(request, p.id);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Results");
  await expect(page.getByLabel("Scenario", { exact: true })).toHaveValue("");
  await expect(page.getByRole("table", { name: "Ranking" })).toBeVisible();
  await page.getByLabel("Weight profile", { exact: true }).selectOption("cost_focus");
  const evaluated = await request.post("/api/evaluate", { data: { project: p, configuration: {
    method: "mavt", scenario_id: null, weight_profile_id: "cost_focus", parameters: {},
  } } });
  const expected = await evaluated.json() as MavtResult;
  await expect(page.getByRole("table", { name: "Ranking" }).locator("tbody tr").first())
    .toContainText(at(expected.ranking, 0).name);
  await openTab(page, "Weights");
  await expect(page.getByText(/Viewing: Cost focus/)).toBeVisible();
  await page.getByLabel("Scenario", { exact: true }).selectOption("linear_defects");
  await openTab(page, "Results");
  await expect(page.getByLabel("Weight profile", { exact: true })).toHaveValue("cost_focus");
  await expect(page.getByLabel("Scenario", { exact: true })).toHaveValue("linear_defects");
  await expect(page.getByRole("table", { name: "Ranking" })).toBeVisible();
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
});

test("changing alternatives prompts a local-anchor swing review", async ({ page, request }) => {
  const p = readJson(VC_FILE) as Project; p.id = "anchor-review-browser"; p.title = "Anchor review test model";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Alternatives");
  await page.getByLabel("New alternative name").fill("Extra option");
  await page.getByRole("button", { name: "Add alternative", exact: true }).click();
  await expect(page.getByRole("button", { name: "Review swing judgements", exact: true })).toBeVisible();
  await expect(page.locator(".banner.warning")).toContainText("Local anchors depend on measurements and alternatives.");
  await page.getByRole("button", { name: "Review swing judgements", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Weights" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "I have reviewed the swing judgements" }).click();
  await expect(page.getByRole("button", { name: "Review swing judgements", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
});

test.afterEach(async ({ request }) => {
  for (const id of ["context-browser", "anchor-review-browser", "fixed-range-banner-browser"]) await request.delete(`/api/projects/${id}`);
});

test("fixed-anchor study profile and same-domain scenario switches never request swing review", async ({ page, request }) => {
  const project = readJson(resolve(REPO, "examples/nz_venture_screening/project.json")) as Project;
  const imported = await request.post("/api/projects/import", { data: project });
  expect([201, 409]).toContain(imported.status());
  const before = await storedFile(request, project.id);
  const documentResponse = await request.get(`/api/projects/${project.id}`);
  const document = await documentResponse.json() as { fingerprint: string };
  await page.goto(`/#/p/${project.id}`);
  await openTab(page, "Results");
  const review = page.getByRole("button", { name: "Review swing judgements", exact: true });
  for (const profile of ["commercial_traction", "technical_ip", ""]) {
    await page.getByLabel("Weight profile", { exact: true }).selectOption(profile);
    await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
    await expect(review).toHaveCount(0);
    await expect(page.locator(".banner.warning")).toHaveCount(0);
  }
  for (const scenario of ["linear_market_size", ""]) {
    await page.getByLabel("Scenario", { exact: true }).selectOption(scenario);
    await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
    await expect(review).toHaveCount(0);
    await openTab(page, "Open Questions");
    await page.getByRole("button", { name: "About: No overall importance score is calculated." }).click();
    await expect(page.getByRole("region", { name: "Open Questions", exact: true })).toContainText("One-way MAVT weight sensitivity");
    await page.getByRole("button", { name: "About: No overall importance score is calculated." }).click();
    await expect(review).toHaveCount(0);
    await openTab(page, "Results");
  }
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
  const after = await request.get(`/api/projects/${project.id}`);
  expect((await after.json() as { fingerprint: string }).fingerprint).toBe(document.fingerprint);
  expect(after.headers().etag).toBe(documentResponse.headers().etag);
});

test("a true fixed-range edit requests review without mentioning local anchors", async ({ page, request }) => {
  const project = readJson(resolve(REPO, "examples/supplier_qualification/project.json")) as Project;
  project.id = "fixed-range-banner-browser";
  expect((await request.post("/api/projects/import", { data: project })).status()).toBe(201);
  const before = await storedFile(request, project.id);
  await page.goto(`/#/p/${project.id}`);
  await selectNode(page, "Unit price");
  await page.getByLabel("Upper bound", { exact: true }).fill("61");
  await page.getByLabel("Upper bound", { exact: true }).press("Enter");
  const banner = page.locator(".banner.warning");
  await expect(banner).toContainText("Preference ranges changed.");
  await expect(banner).not.toContainText("Local anchors");
  await page.getByRole("button", { name: "I have reviewed the swing judgements", exact: true }).click();
  await expect(banner).toHaveCount(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
});
