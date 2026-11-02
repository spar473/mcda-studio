import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { buildTwoOptionModel, openTab, waitIdle, readJson, REPO, storedFile } from "./helpers";
import type { Project } from "../src/api/types";

test("open questions identify a missing measurement without treating it as zero", async ({ page }) => {
  await buildTwoOptionModel(page, "Open questions example");
  await openTab(page, "Measurements");
  const cell = page.getByLabel("Alpha on Quality", { exact: true });
  await cell.fill("");
  await cell.press("Enter");
  await waitIdle(page);
  await openTab(page, "Open Questions");
  const panel = page.getByRole("region", { name: "Open Questions" });
  await expect(panel.getByText("What is Alpha's measurement for Quality?")).toBeVisible();
  await expect(panel.getByLabel("Questions limitations")).toContainText("could not run");
  await panel.getByRole("button", { name: "Open measurements" }).click();
  await expect(page.getByLabel("Alpha on Quality", { exact: true })).toBeVisible();
});

test("class questions link to classes and viewing preserves stored project bytes", async ({ page, request }) => {
  const project = readJson(resolve(REPO, "examples/supplier_qualification/project.json")) as Project;
  project.id = "questions-supplier-range";
  const imported = await request.post("/api/projects/import", { data: project });
  expect(imported.status()).toBe(201);
  const { fingerprint } = await imported.json() as { fingerprint: string };
  const before = await storedFile(request, project.id);
  await page.goto(`/#/p/${project.id}`);
  await openTab(page, "Open Questions");
  const panel = page.getByRole("region", { name: "Open Questions" });
  await expect(panel.getByText("One-way class-boundary sensitivity", { exact: false })).toBeVisible();
  const dossier = readJson(resolve(REPO, "examples/evidence_demo/supplier.json")) as { project_fingerprint: string; claims: { value: number; uncertainty_lower: number; uncertainty_upper: number }[] };
  dossier.project_fingerprint = fingerprint;
  const claim = dossier.claims[0];
  if (!claim) throw new Error("Example dossier has no claim");
  claim.value = 42;
  claim.uncertainty_lower = 20;
  claim.uncertainty_upper = 60;
  await panel.getByLabel("Evidence dossier (optional)").setInputFiles({ name: "range.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(dossier)) });
  await expect(panel.getByText(/can change the alternative's rank and class/)).toBeVisible();
  await panel.getByText("Measurement range analysis", { exact: true }).click();
  await expect(panel.getByLabel("Range witnesses")).toContainText("rank");
  await expect(panel.getByLabel("Range boundary contacts")).toContainText("Class boundary for");
  await panel.getByRole("button", { name: "Open classes", exact: true }).first().click();
  await expect(page.getByRole("button", { name: "Apply classes" })).toBeVisible();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
});

test("local evidence dossier surfaces unreviewed and conflicting claims without editing the project", async ({ page, request }) => {
  const project = readJson(resolve(REPO, "examples/nz_deeptech_vc/project.json")) as Project;
  project.id = "questions-vc-evidence";
  const imported = await request.post("/api/projects/import", { data: project });
  expect(imported.status()).toBe(201);
  const { fingerprint } = await imported.json() as { fingerprint: string };
  const before = await storedFile(request, project.id);
  await page.goto(`/#/p/${project.id}`);
  await openTab(page, "Open Questions");
  const dossier = readJson(resolve(REPO, "examples/evidence_demo/vc.json")) as { project_fingerprint: string };
  dossier.project_fingerprint = fingerprint;
  await page.getByLabel("Evidence dossier (optional)").setInputFiles({ name: "vc.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(dossier)) });
  const panel = page.getByRole("region", { name: "Open Questions" });
  await expect(panel.getByText("Should claim unreviewed_example be accepted, corrected or rejected?")).toBeVisible();
  await expect(panel.getByText("Which conflicting claim is supported?")).toBeVisible();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
});
