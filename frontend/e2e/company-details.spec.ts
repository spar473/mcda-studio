import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { AnySensitivityResult, EvidenceDossier, Project, ScreeningDetails } from "../src/api/types";
import { openTab, readJson, REPO, saveState, storedFile } from "./helpers";

const project = readJson(resolve(REPO, "examples/nz_venture_screening/project.json")) as Project;
const dossier = readJson(resolve(REPO, "examples/nz_venture_screening/evidence.json")) as EvidenceDossier;
const endpoint = `/api/projects/${project.id}`;
async function start(page: Page, request: APIRequestContext) {
  await page.goto("/");
  await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: project.title, exact: true })).toBeVisible();
  await openTab(page, "Results"); await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
  return { file: await storedFile(request, project.id), response: await request.get(endpoint) };
}
async function intact(page: Page, request: APIRequestContext, before: Awaited<ReturnType<typeof start>>) {
  const after = await request.get(endpoint);
  expect(await after.json()).toEqual(await before.response.json()); expect(after.headers().etag).toBe(before.response.headers().etag);
  expect((await storedFile(request, project.id)).equals(before.file)).toBe(true);
  await expect(saveState(page)).toHaveText("All changes saved"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
}
function responseFor(page: Page, id: string, withDossier = false) {
  return page.waitForResponse(response => {
    if (!response.url().endsWith("/api/screening-details") || response.request().method() !== "POST") return false;
    const body = response.request().postDataJSON() as { alternative_id?: string; dossier?: unknown };
    return body.alternative_id === id && (!withDossier || Boolean(body.dossier));
  });
}
async function openDetail(page: Page, trigger: Locator, id: string, name: string) {
  const response = responseFor(page, id); await trigger.click();
  const data = await (await response).json() as ScreeningDetails;
  const dialog = page.getByRole("dialog", { name, exact: true });
  await expect(dialog.getByRole("region", { name: "Alternative contributions", exact: true }).locator("li")).toHaveCount(16);
  if (!data.alternative) throw Error("missing alternative detail");
  await expect(dialog.getByText(data.alternative.row.value.toFixed(4), { exact: true })).toBeVisible();
  if (id === "hnry") {
    const requirements = dialog.getByRole("region", { name: "Alternative requirements", exact: true });
    await expect(requirements).toContainText("fails"); await expect(requirements).toContainText("Series B or later");
    await expect(requirements).toContainText("Pre-seed, Seed, Series A"); await expect(requirements).not.toContainText("['");
  }
  return { dialog, data };
}

test("company triggers share complete screening detail and loaded sources without changing saved state", async ({ page, request }) => {
  test.setTimeout(120_000);
  const before = await start(page, request);
  const families = ["summary", "ranking", "contribution", "feasibility", "comparison", "evidence", "questions"] as const;
  let loaded = false;
  for (const family of families) {
    if (family === "comparison") { await page.getByLabel("Method", { exact: true }).selectOption("promethee2"); await openTab(page, "Compare"); }
    else if (family === "evidence") await openTab(page, "Evidence");
    else if (family === "questions") await openTab(page, "Open Questions");
    else await openTab(page, "Results");
    for (const [id, name] of [["upstock", "Upstock"], ["hnry", "Hnry"]] as const) {
      let trigger: Locator;
      if (family === "summary") trigger = page.getByRole("table", { name: "Screening summary", exact: true }).getByRole("button", { name, exact: true });
      else if (family === "ranking") trigger = page.getByRole("group", { name: "Overall MAVT values", exact: true }).locator(`g[data-alternative-id="${id}"]`);
      else if (family === "contribution") trigger = page.getByRole("group", { name: "Weighted leaf contributions", exact: true }).locator(`g[data-alternative-id="${id}"] rect[data-contribution]:not([data-contribution="0"])`).first();
      else if (family === "feasibility") trigger = page.getByRole("table", { name: "Feasibility by alternative", exact: true }).getByRole("button", { name, exact: true });
      else if (family === "comparison") trigger = page.getByRole("table", { name: "Methods side by side", exact: true }).getByRole("button", { name, exact: true });
      else if (family === "evidence") trigger = page.getByLabel("Evidence claims", { exact: true }).getByRole("heading", { name, exact: true }).getByRole("button");
      else trigger = page.getByRole("region", { name: "Open Questions", exact: true }).getByRole("heading", { name, exact: true }).getByRole("button");
      const opener = await trigger.elementHandle();
      const { dialog } = await openDetail(page, trigger, id, name);
      if (family === "comparison") await expect(dialog).toContainText("MAVT screening detail");
      if (!loaded) {
        const result = responseFor(page, id, true);
        await dialog.getByRole("button", { name: "Load the study's evidence", exact: true }).click();
        const data = await (await result).json() as ScreeningDetails;
        const rating = data.alternative?.ratings.find(r => typeof r.measurement === "string" && r.claim_ids.length);
        if (!rating) throw Error("missing sourced rubric");
        const sources = dialog.getByRole("region", { name: "Alternative ratings and sources", exact: true });
        const block = sources.locator("details").filter({ has: page.locator("summary", { hasText: rating.name }) }).first();
        await block.locator(":scope > summary").click();
        await expect(block.locator(":scope > p").first()).toHaveText(rating.rubric_text);
        const claim = dossier.claims.find(c => c.id === rating.claim_ids[0]); if (!claim) throw Error("missing original claim");
        await expect(block).toContainText(claim.source.date); await expect(block).toContainText(claim.source.description);
        if (/^https?:\/\//i.test(claim.source.reference)) await expect(block.getByRole("link", { name: claim.source.name, exact: true })).toHaveAttribute("href", claim.source.reference);
        loaded = true;
      }
      await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
      if (await opener.evaluate(element => element.isConnected)) await expect(trigger).toBeFocused();
      else await expect(page.getByRole("tab", { selected: true })).toBeFocused();
    }
  }
  await openTab(page, "Evidence");
  await expect(page.getByRole("button", { name: "Open the study's evidence", exact: true })).toHaveCount(0);
  await expect(page.getByText("Review history (0 appended)", { exact: true })).toBeVisible();
  await intact(page, request, before);
});

test("keyboard company exploration probes the exact backend weight and crossover", async ({ page, request }) => {
  const before = await start(page, request);
  const opener = page.getByRole("table", { name: "Screening summary", exact: true }).getByRole("button", { name: "Upstock", exact: true });
  const response = responseFor(page, "upstock"); await opener.focus(); await page.keyboard.press("Space");
  const detail = await (await response).json() as ScreeningDetails, change = detail.alternative?.row.fragility;
  if (change?.status !== "change" || !change.criterion_id || change.local_weight === null) throw Error("missing exact fragility");
  const dialog = page.getByRole("dialog", { name: "Upstock", exact: true });
  const exact = page.waitForRequest(r => r.url().endsWith("/api/sensitivity/probe") && (r.postDataJSON() as { weight: number }).weight === change.local_weight);
  const sweepResponse = page.waitForResponse(r => r.url().endsWith("/api/sensitivity") && r.request().method() === "POST");
  await dialog.getByRole("button", { name: "Show in Sensitivity", exact: true }).click();
  expect((await exact).postDataJSON() as { node_id: string; weight: number }).toMatchObject({ node_id: change.criterion_id, weight: change.local_weight });
  const sweep = await (await sweepResponse).json() as AnySensitivityResult;
  await expect(page.getByLabel("Hypothetical local weight", { exact: true })).toHaveValue(change.local_weight.toFixed(4));
  const crossover = sweep.crossovers[0]; if (!crossover) throw Error("missing crossover");
  const root = page.waitForRequest(r => r.url().endsWith("/api/sensitivity/probe") && (r.postDataJSON() as { weight: number }).weight === crossover.weight);
  const row = page.getByRole("list", { name: "Exact crossovers" }).getByRole("button").first();
  await row.focus(); await page.keyboard.press("Space");
  expect((await root).postDataJSON() as { weight: number }).toMatchObject({ weight: crossover.weight });
  await intact(page, request, before);
});

test("presentation alternative detail shares the study evidence and Escape keeps the presentation open", async ({ page, request }) => {
  test.setTimeout(60_000);
  const before = await start(page, request);
  await page.getByRole("button", { name: "Builder view", exact: true }).click();
  await expect(page.getByRole("button", { name: "Builder view", exact: true })).toHaveAttribute("aria-pressed", "true");
  await openTab(page, "Model"); await page.getByRole("button", { name: "Present", exact: true }).click();
  await expect(page.getByRole("button", { name: "Exit presentation", exact: true })).toBeVisible();
  const trigger = page.getByRole("table", { name: "Screening summary", exact: true }).getByRole("button", { name: "Upstock", exact: true });
  const opener = await trigger.elementHandle();
  const { dialog } = await openDetail(page, trigger, "upstock", "Upstock");
  const loaded = responseFor(page, "upstock", true);
  await dialog.getByRole("button", { name: "Load the study's evidence", exact: true }).click(); await loaded;
  await expect(dialog.getByRole("button", { name: "Load the study's evidence", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
  if (await opener.evaluate(element => element.isConnected)) await expect(trigger).toBeFocused();
  else await expect(page.getByRole("heading", { level: 2, name: project.title, exact: true })).toBeFocused();
  await expect(page.getByRole("button", { name: "Exit presentation", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Exit presentation", exact: true }).click(); await openTab(page, "Evidence");
  await expect(page.getByLabel("Evidence claims", { exact: true }).locator("li[data-claim-id]")).toHaveCount(dossier.claims.length);
  await expect(page.getByText("Review history (0 appended)", { exact: true })).toBeVisible();
  await intact(page, request, before);
});
