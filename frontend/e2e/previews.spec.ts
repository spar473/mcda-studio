import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import type { Project, WeightPreview } from "../src/api/types";
import { VC_FILE, REPO, at, openTab, readJson, saveState, selectNode, storedFile } from "./helpers";

test("incomplete projects expose engine previews without changing stored data", async ({ page, request }, testInfo) => {
  const p = readJson(resolve(REPO, "examples/supplier_selection/project.json")) as Project;
  p.id = "preview-browser"; p.title = "Preview acceptance model"; p.performances = [];
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const original = await storedFile(request, p.id);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Weights");
  const http = await request.post("/api/weights/preview", { data: { project: p } });
  const weights = await http.json() as WeightPreview;
  expect(weights.weights_ready).toBe(true);
  const globals = page.locator("table td.num:nth-child(4)");
  await expect.poll(async () => (await globals.allInnerTexts()).filter(Boolean).sort()).toEqual(Object.values(weights.global_weights).map((v) => v.toFixed(4)).sort());
  await page.screenshot({ path: testInfo.outputPath("b1-incomplete-weights.png") });
  const criterion = at(p.criteria.filter((c) => c.id === "unit_price"), 0);
  await selectNode(page, criterion.name);
  const preview = page.getByRole("region", { name: "Value-function preview" });
  await expect(preview).toContainText("Function ready");
  await expect(preview).toContainText("Measurements incomplete");
  await expect(preview).toContainText("Effective domain:");
  await preview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("b1-fixed-preview.png") });
  await openTab(page, "Results"); await expect(page.getByRole("table", { name: "Ranking" })).toHaveCount(0);
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(original)).toBe(true);
  await request.delete(`/api/projects/${p.id}`);
});


test("a missing local measurement cannot produce a resolved preview", async ({ page, request }, testInfo) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "local-preview-browser"; p.title = "Local preview acceptance";
  p.performances = p.performances.filter((m) => !(m.criterion_id === "market_growth" && m.alternative_id === "hyades"));
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  await page.goto(`/#/p/${p.id}`); await selectNode(page, "Market Growth");
  const preview = page.getByRole("region", { name: "Value-function preview" });
  await expect(preview).toContainText("Function unavailable");
  await expect(preview).toContainText("MISSING_MEASUREMENT");
  await expect(preview).not.toContainText("Effective domain:");
  await preview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("b1-local-unresolved.png") });
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await request.delete(`/api/projects/${p.id}`);
});
