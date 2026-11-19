// The venture screening study in the real application: the bundled project opens with its two
// partner profiles, classes, the requirements check beside the ranking (Hnry fails the stage
// mandate and keeps its place), every method in Compare (AHP deliberately not set up), the study's
// evidence dossier with its two open conflicts, and Open Questions. Every number shown comes from
// the engine; the expectations are the README's documented reading of the built study.
import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import type { Project } from "../src/api/types";
import { evidenceClaim, openTab, readRanking, readJson, REPO } from "./helpers";

const EXAMPLE = resolve(REPO, "examples", "nz_venture_screening");

test("venture screening study: profiles, classes, mandate beside the ranking, methods and evidence", async ({ page, request }) => {
  const project = readJson(resolve(EXAMPLE, "project.json")) as Project;
  const imported = await request.post("/api/projects/import", { data: project });
  expect([201, 409]).toContain(imported.status());
  const before = (await (await request.get(`/api/projects/${project.id}`)).json() as { fingerprint: string }).fingerprint;
  await page.goto(`/#/p/${project.id}`);
  await expect(page.getByRole("heading", { level: 1, name: project.title, exact: true })).toBeVisible();

  // --- Results: the Technical/IP-led profile is the automatic default ---
  await openTab(page, "Results");
  const technical = await readRanking(page);
  expect(technical.map((r) => r.name)).toEqual([
    "Upstock", "Wellumio", "Hectre", "Wych", "Captivate Technology", "Scentian Bio", "Hnry", "Kea Aerospace",
  ]);
  const feasibility = page.getByRole("region", { name: "Feasibility beside the ranking" })
    .getByRole("table", { name: "Feasibility by alternative" });
  await expect(feasibility.getByRole("row", { name: /^Hnry/ }).locator("td").first()).toHaveText("fails");
  await expect(feasibility.getByRole("row", { name: /^Upstock/ }).locator("td").first()).toHaveText("passes");

  // --- the Commercial/traction-led profile reorders the middle of the queue ---
  await page.getByLabel("Weight profile", { exact: true }).selectOption("commercial_traction");
  await expect.poll(async () => (await readRanking(page)).map((r) => r.name)).toEqual([
    "Upstock", "Hectre", "Wych", "Hnry", "Wellumio", "Captivate Technology", "Scentian Bio", "Kea Aerospace",
  ]);
  // looking at another profile never changes the project
  const after = (await (await request.get(`/api/projects/${project.id}`)).json() as { fingerprint: string }).fingerprint;
  expect(after).toBe(before);

  // --- Compare: every method reads the same model; AHP is not set up on this study ---
  await openTab(page, "Compare");
  const methods = page.getByRole("table", { name: "Methods side by side" });
  await expect(methods).toContainText("Upstock");
  await expect(methods.locator("td[data-method='ahp']").first()).toContainText("AHP is not set up for this model");

  // --- Evidence: the study's dossier binds, with two open conflicts ---
  await openTab(page, "Evidence");
  const panel = page.getByRole("region", { name: "Evidence Workspace", exact: true });
  // The project is exactly the starter's worked example, so its dossier opens in one action.
  await panel.getByRole("button", { name: "Open the study's evidence", exact: true }).click();
  const claims = panel.getByLabel("Evidence claims");
  await evidenceClaim(panel, "disputed_kea_stage");
  await expect(claims).toContainText("disputed_kea_stage");
  await evidenceClaim(panel, "disputed_scentian_market");
  await expect(claims).toContainText("disputed_scentian_market");

  // --- Open Questions lists the outdated and conflicting claims from that dossier ---
  await openTab(page, "Open Questions");
  const questions = page.getByRole("region", { name: "Open Questions" });
  await expect(questions).toContainText("Upstock");
});
