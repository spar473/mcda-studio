import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { Project } from "../src/api/types";
import { REPO, openTab, readJson, storedFile } from "./helpers";

const SUPPLIER_FILE = resolve(REPO, "examples/supplier_selection/project.json");
const unavailable = { status: 503, json: { error: { code: "TEST_UNAVAILABLE", message: "Analysis service unavailable for test", details: [] } } };

async function load(request: APIRequestContext, page: Page, id: string): Promise<Buffer> {
  const p = readJson(SUPPLIER_FILE) as Project; p.id = id;
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${id}`);
  return storedFile(request, id);
}
/** Fails only the first matching request, then lets every later one reach the real engine. */
async function failOnce(page: Page, pattern: string): Promise<() => number> {
  let calls = 0;
  await page.route(pattern, async route => { calls += 1; if (calls === 1) await route.fulfill(unavailable); else await route.continue(); });
  return () => calls;
}
async function unchanged(page: Page, request: APIRequestContext, id: string, before: Buffer) {
  expect((await storedFile(request, id)).equals(before)).toBe(true);
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  await request.delete(`/api/projects/${id}`);
}

test("a failed analysis record recovers with Retry, without changing the project", async ({ page, request }) => {
  const calls = await failOnce(page, "**/api/analysis/record");
  const before = await load(request, page, "retry-record"); await openTab(page, "Results");
  await expect(page.getByRole("alert")).toContainText("Analysis service unavailable for test");
  await page.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0); expect(calls()).toBe(2);
  await unchanged(page, request, "retry-record", before);
});

test("a failed scoped analysis check recovers with Retry before results appear", async ({ page, request }) => {
  const calls = await failOnce(page, "**/api/analysis/validate");
  const before = await load(request, page, "retry-validate"); await openTab(page, "Results");
  await expect(page.getByRole("alert")).toContainText("Analysis service unavailable for test");
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Retry analysis check", exact: true }).click();
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toBeVisible(); expect(calls()).toBe(2);
  await unchanged(page, request, "retry-validate", before);
});

test("a failed sensitivity sweep recovers with Retry for the same criterion", async ({ page, request }) => {
  const calls = await failOnce(page, "**/api/sensitivity");
  const before = await load(request, page, "retry-sensitivity"); await openTab(page, "Sensitivity");
  await page.getByLabel("Criterion to vary").selectOption("cost");
  await expect(page.getByRole("alert")).toContainText("Analysis service unavailable for test");
  await page.getByRole("button", { name: "Retry sensitivity", exact: true }).click();
  await expect(page.getByLabel("Hypothetical local weight")).toBeVisible();
  await expect(page.getByLabel("Criterion to vary")).toHaveValue("cost"); expect(calls()).toBe(2);
  await unchanged(page, request, "retry-sensitivity", before);
});
