import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { ProfileComparison, Project, ScreeningDetails } from "../src/api/types";
import { openTab, readJson, REPO, saveState, storedFile } from "./helpers";

const study = readJson(resolve(REPO, "examples/nz_venture_screening/project.json")) as Project;
async function snapshot(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/projects/${id}`);
  return { body: await response.json() as unknown, etag: response.headers().etag, file: await storedFile(request, id) };
}
async function unchanged(page: Page, request: APIRequestContext, id: string, before: Awaited<ReturnType<typeof snapshot>>) {
  const after = await snapshot(request, id);
  expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
  await expect(saveState(page)).toHaveText("All changes saved"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
}
function comparisonResponse(page: Page) {
  return page.waitForResponse(response => response.url().endsWith("/api/screening-summary/profiles") && response.request().method() === "POST");
}
function detailResponse(page: Page, id: string, profile: string) {
  return page.waitForResponse(response => {
    if (!response.url().endsWith("/api/screening-details") || response.request().method() !== "POST") return false;
    const body = response.request().postDataJSON() as { alternative_id?: string; configuration?: { weight_profile_id?: string | null } };
    return body.alternative_id === id && body.configuration?.weight_profile_id === profile;
  });
}

test("partner readings use separate engine ranks and endpoint profiles without changing the saved model", async ({ page, request }) => {
  test.setTimeout(90_000); await page.goto("/");
  await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click(); await openTab(page, "Results");
  const before = await snapshot(request, study.id), received = comparisonResponse(page);
  await page.getByRole("checkbox", { name: "Compare profiles", exact: true }).check();
  const compared = await (await received).json() as ProfileComparison;
  const region = page.getByRole("region", { name: "Profile comparison", exact: true });
  const table = region.getByRole("table", { name: "Profile rankings and movements", exact: true });
  await expect(table.locator("tbody tr")).toHaveCount(8);
  const [left, right] = compared.profiles; if (!left || !right) throw Error("Partner readings missing");
  expect([left.profile_id, right.profile_id]).toEqual(["technical_ip", "commercial_traction"]);
  for (const movement of compared.movements) {
    await expect(region.locator(`g[data-company-id="${movement.alternative_id}"] > path`)).toHaveAttribute("stroke-width", movement.emphasize ? "4" : "1.5");
  }
  for (const alternative of left.summary.rows) {
    const other = right.summary.rows.find(row => row.alternative_id === alternative.alternative_id); if (!other) throw Error("Other endpoint missing");
    const row = table.locator("tbody tr").filter({ has: page.locator(`th button[data-company-id="${alternative.alternative_id}"]`) });
    await expect(row.locator("td").nth(0)).toHaveText(`${String(alternative.rank)} · ${alternative.value.toFixed(4)}${alternative.class_name ? ` · ${alternative.class_name}` : ""}`);
    await expect(row.locator("td").nth(1)).toHaveText(`${String(other.rank)} · ${other.value.toFixed(4)}${other.class_name ? ` · ${other.class_name}` : ""}`);
  }
  const hnry = right.summary.rows.find(row => row.alternative_id === "hnry"); if (!hnry) throw Error("Hnry missing");
  const rightDetail = detailResponse(page, "hnry", right.profile_id);
  const rightEndpoint = region.locator('g[data-company-id="hnry"] > g[role="button"]').last();
  await rightEndpoint.focus(); await page.keyboard.press("Space"); const detail = await (await rightDetail).json() as ScreeningDetails;
  expect(detail.alternative?.row).toEqual(hnry);
  const drawer = page.getByRole("dialog", { name: "Hnry", exact: true }); await expect(drawer).toContainText("Commercial/traction-led");
  await expect(page.getByLabel("Weight profile", { exact: true })).toHaveValue("");
  await page.keyboard.press("Escape"); await expect(drawer).toHaveCount(0);
  const leftDetail = detailResponse(page, "hnry", left.profile_id);
  await region.locator('g[data-company-id="hnry"] > path').click(); await leftDetail;
  await expect(page.getByRole("dialog", { name: "Hnry", exact: true })).toContainText("Technical/IP-led");
  await page.keyboard.press("Escape");
  const upstockDetail = detailResponse(page, "upstock", right.profile_id);
  await region.locator('g[data-company-id="upstock"] > g[role="button"]').last().click();
  const upstock = await (await upstockDetail).json() as ScreeningDetails, change = upstock.alternative?.row.fragility;
  if (change?.status !== "change" || !change.criterion_id || change.local_weight === null) throw Error("Exact profile-specific change missing");
  const probe = page.waitForRequest(value => value.url().endsWith("/api/sensitivity/probe") && (value.postDataJSON() as { weight: number }).weight === change.local_weight);
  await page.getByRole("dialog", { name: "Upstock", exact: true }).getByRole("button", { name: "Show in Sensitivity", exact: true }).click();
  const body = (await probe).postDataJSON() as { node_id: string; weight: number; configuration: { weight_profile_id: string | null } };
  expect(body).toMatchObject({ node_id: change.criterion_id, weight: change.local_weight, configuration: { weight_profile_id: right.profile_id } });
  await expect(page.getByLabel("Weight profile", { exact: true })).toHaveValue(right.profile_id);
  await unchanged(page, request, study.id, before);
});

test("generic tied readings, any two of three profiles, and absent classes stay explicit and read-only", async ({ page, request }) => {
  test.setTimeout(60_000); const project = structuredClone(study); project.id = "partner-tied-generic"; project.sorting = null; project.analysis = { ...project.analysis, method: "mavt" };
  const firstAlternative = project.alternatives[0], firstProfile = project.weight_profiles[0]; if (!firstAlternative || !firstProfile) throw Error("Fixture missing");
  const raw = new Map(project.performances.filter(performance => performance.alternative_id === firstAlternative.id).map(performance => [performance.criterion_id, performance.value]));
  project.performances = project.performances.map(performance => ({ ...performance, value: raw.get(performance.criterion_id) ?? performance.value }));
  project.weight_profiles.push({ ...structuredClone(firstProfile), id: "third", name: "Third partner" });
  expect((await request.post("/api/projects/import", { data: project })).status()).toBe(201);
  const before = await snapshot(request, project.id); await page.goto(`/#/p/${project.id}`); await openTab(page, "Results");
  let received = comparisonResponse(page); await page.getByRole("checkbox", { name: "Compare profiles", exact: true }).check(); await received;
  received = comparisonResponse(page); await page.getByLabel("Right profile", { exact: true }).selectOption("third");
  const result = await (await received).json() as ProfileComparison;
  expect(result.profiles.map(profile => profile.profile_id)).toEqual(["technical_ip", "third"]);
  expect(result.profiles.every(profile => profile.summary.rows.every(row => row.rank === 1 && row.class_id === null))).toBe(true);
  expect(result.movements.every(movement => movement.places_changed === 0 && !movement.emphasize)).toBe(true);
  const region = page.getByRole("region", { name: "Profile comparison", exact: true }); await expect(region.getByRole("table").locator("tbody tr")).toHaveCount(8);
  for (const alternative of project.alternatives) await expect(region.locator(`g[data-company-id="${alternative.id}"] > path`)).toHaveAttribute("d", "M 286 52 L 614 52");
  await expect(region.getByLabel("Profile class colours", { exact: true })).toHaveCount(0);
  await unchanged(page, request, project.id, before);
});
