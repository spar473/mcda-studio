import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { EvidenceDossier, EvidenceWorkspace, Project } from "../src/api/types";
import { evidenceClaim, openTab, readJson, REPO, saveState, storedFile } from "./helpers";

const study = readJson(resolve(REPO, "examples/nz_venture_screening/project.json")) as Project;
const dossier = readJson(resolve(REPO, "examples/nz_venture_screening/evidence.json")) as EvidenceDossier;
const analystTabs = ["Results", "Sensitivity", "Compare", "Reference cases", "Evidence", "Open Questions", "Decision"];
async function gallery(page: Page) {
  await page.goto("/"); await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click();
  await expect(page.getByRole("button", { name: "Analyst view", exact: true })).toHaveAttribute("aria-pressed", "true");
}
async function snapshot(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/projects/${id}`);
  return { body: await response.json() as unknown, etag: response.headers().etag, file: await storedFile(request, id) };
}
async function unchanged(request: APIRequestContext, id: string, before: Awaited<ReturnType<typeof snapshot>>) {
  const after = await snapshot(request, id);
  expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
}

test("worked-gallery mode overrides an earlier choice, reconciles hidden tabs, and reload retains the explicit session choice", async ({ page, request }) => {
  await page.addInitScript(id => sessionStorage.setItem(`mcda:editor-view:${id}`, "builder"), study.id);
  await gallery(page); expect(await page.getByRole("tab").allTextContents()).toEqual(analystTabs);
  await expect(page.getByRole("heading", { name: "Build", exact: true })).toHaveCount(0);
  const before = await snapshot(request, study.id);
  await page.getByRole("button", { name: "Builder view", exact: true }).click(); await openTab(page, "Model");
  await page.getByRole("button", { name: "Analyst view", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Results", exact: true })).toHaveAttribute("aria-selected", "true");
  expect(await page.getByRole("tab").allTextContents()).toEqual(analystTabs);
  await page.getByRole("button", { name: "Builder view", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Results", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.reload(); await expect(page.getByRole("button", { name: "Builder view", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("tab", { name: "Model", exact: true })).toHaveAttribute("aria-selected", "true");
  await unchanged(request, study.id, before); await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});

test("a direct import with the study title starts Builder and a deliberate Analyst choice survives reload", async ({ page, request }) => {
  const project = { ...study, id: "ordinary-view-source" };
  expect((await request.post("/api/projects/import", { data: project })).status()).toBe(201);
  const before = await snapshot(request, project.id);
  await page.goto(`/#/p/${project.id}`); await expect(page.getByRole("button", { name: "Builder view", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Analyst view", exact: true }).click(); expect(await page.getByRole("tab").allTextContents()).toEqual(analystTabs);
  await page.reload(); await expect(page.getByRole("button", { name: "Analyst view", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await page.getByRole("tab").allTextContents()).toEqual(analystTabs);
  await unchanged(request, project.id, before); await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});

test("both view switches retain an actual unexported evidence review and its dirty state without changing project data", async ({ page, request }) => {
  test.setTimeout(90_000); await gallery(page); const before = await snapshot(request, study.id);
  await openTab(page, "Evidence"); const panel = page.getByRole("region", { name: "Evidence Workspace", exact: true });
  await panel.getByRole("button", { name: "Open the study's evidence", exact: true }).click();
  const claim = dossier.claims[0]; if (!claim) throw Error("Study claim missing");
  await (await evidenceClaim(panel, claim.id)).getByRole("button", { name: /^Review / }).click();
  await panel.getByLabel("Reviewer", { exact: true }).fill("View mode reviewer");
  await panel.getByLabel("Review decision", { exact: true }).selectOption("rejected");
  await panel.getByLabel("Review note").fill("Temporary review retained across views");
  await panel.getByRole("button", { name: "Preview review", exact: true }).click();
  await expect(panel.getByLabel("Proposed review", { exact: true })).toContainText("rejected");
  await panel.getByRole("button", { name: "Confirm review in workspace", exact: true }).click();
  for (const mode of ["Builder view", "Analyst view"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    await expect(panel.getByText("Review history (1 appended)", { exact: true })).toBeVisible();
    await expect(await evidenceClaim(panel, claim.id)).toContainText("rejected");
    await expect(saveState(page)).toHaveText("● Unsaved changes"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
    await unchanged(request, study.id, before);
  }
  const downloaded = page.waitForEvent("download"); await panel.getByRole("button", { name: "Export review workspace", exact: true }).click();
  const file = await (await downloaded).path(); if (!file) throw Error("Review workspace download missing");
  const workspace = JSON.parse(readFileSync(file, "utf8")) as EvidenceWorkspace;
  expect(workspace.original_dossier).toEqual(dossier); expect(workspace.reviews).toHaveLength(1);
  expect(workspace.reviews[0]).toMatchObject({ claim_id: claim.id, review: { reviewer: "View mode reviewer", status: "rejected", note: "Temporary review retained across views" } });
  await expect(saveState(page)).toHaveText("All changes saved"); await unchanged(request, study.id, before);
});
