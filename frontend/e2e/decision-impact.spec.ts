import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import type { DecisionImpact, ProjectDocument } from "../src/api/types";
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

test("Sort by decision impact is opt-in, reads the new route in Python's order, and changes nothing", async ({ page, request }) => {
  test.setTimeout(120_000); await gallery(page);
  const before = await snapshot(request), calls: string[] = [], writes: string[] = [];
  page.on("request", value => {
    if (value.url().endsWith("/api/decision-impact")) calls.push(value.url());
    if (value.url().endsWith("/api/edit") || ["PUT", "DELETE"].includes(value.method()) && value.url().includes(`/api/projects/${id}`)) writes.push(value.url());
  });
  await openTab(page, "Open Questions");
  const region = page.getByRole("region", { name: "Open Questions" });
  await expect(region.getByText(/MAVT first place can change|Should claim|Is claim/).first()).toBeVisible();
  const toggle = region.getByRole("checkbox", { name: "Sort by decision impact", exact: true });
  await expect(toggle).not.toBeChecked(); expect(calls).toEqual([]);
  const received = page.waitForResponse(value => value.url().endsWith("/api/decision-impact") && value.request().method() === "POST");
  await toggle.check();
  const impact = await (await received).json() as DecisionImpact; expect(impact.status).toBe("available");
  const list = region.getByRole("region", { name: "Decision impact", exact: true });
  await expect(list).toBeVisible();
  const items = list.locator("ol > li");
  await expect(items).toHaveCount(impact.cells.length); expect(impact.cells.length).toBe(112);
  const headings = await items.locator("strong").allTextContents();
  impact.cells.forEach((cell, index) => expect(headings[index]).toContain(cell.alternative_name));
  await expect(items.first()).toContainText("Could change the leader or a class");
  await expect(items.last()).toContainText("No other label changes a rank, the leader or a class");
  const tiers = impact.cells.map(cell => cell.tier), order = { leader_or_class: 0, rank: 1, none: 2 } as const;
  expect(tiers).toEqual([...tiers].sort((a, b) => order[a] - order[b]));
  expect(calls.length).toBe(1);
  await toggle.uncheck(); await expect(list).toHaveCount(0);
  expect(writes).toEqual([]);
  const after = await snapshot(request);
  expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
  await expect(saveState(page)).toHaveText("All changes saved"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});
