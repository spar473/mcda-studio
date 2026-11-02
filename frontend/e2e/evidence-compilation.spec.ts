import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { EvidenceCompilation, EvidenceDossier, Project, ProjectCopyReceipt, ProjectDocument } from "../src/api/types";
import { openTab, readJson, REPO, storedFile } from "./helpers";

/** The exact bundled project its dossier was written for; never a fingerprint rewrite. */
async function pairedProject(request: APIRequestContext, example: string, dossier: EvidenceDossier): Promise<Project> {
  const project = readJson(resolve(REPO, `examples/${example}/project.json`)) as Project;
  const imported = await request.post("/api/projects/import", { data: project });
  expect([201, 409]).toContain(imported.status()); // an earlier spec may have added the same example
  const stored = await (await request.get(`/api/projects/${project.id}`)).json() as ProjectDocument;
  expect(stored.fingerprint).toBe(dossier.project_fingerprint);
  return stored.project;
}

async function downloaded(page: Page, click: () => Promise<void>): Promise<{ path: string; value: unknown }> {
  const event = page.waitForEvent("download");
  await click();
  const path = await (await event).path();
  if (!path) throw Error("Download missing");
  return { path, value: JSON.parse(readFileSync(path, "utf8")) };
}

for (const [name, example] of [["vc", "nz_deeptech_vc"], ["supplier", "supplier_qualification"]] as const) {
  test(`${name} evidence compiles into a separate copy whose import is verified against its bundle`, async ({ page, request }, testInfo) => {
    const dossierPath = resolve(REPO, `examples/evidence_demo/${name}.json`);
    const dossier = readJson(dossierPath) as EvidenceDossier;
    const project = await pairedProject(request, example, dossier);
    const accepted = dossier.claims[0];
    if (!accepted) throw Error("Demo claim missing");
    const before = await storedFile(request, project.id);
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Evidence");
    const panel = page.getByRole("region", { name: "Evidence Workspace", exact: true });
    await panel.getByLabel("Evidence dossier or review workspace").setInputFiles(dossierPath);
    await expect(panel.getByLabel("Evidence claims")).toContainText("Proposed by");
    // Acceptance is a review; compilation is a separate, acknowledged step.
    await panel.getByRole("button", { name: "Review unreviewed_example", exact: true }).click();
    await panel.getByLabel("Reviewer", { exact: true }).fill("Demonstration reviewer");
    await panel.getByLabel("Review decision", { exact: true }).selectOption("rejected");
    await panel.getByRole("button", { name: "Preview review", exact: true }).click();
    await panel.getByRole("button", { name: "Confirm review in workspace" }).click();
    await expect(panel.getByText("Review history (1 appended)", { exact: true })).toBeVisible();
    const changes = panel.getByRole("table", { name: "Measurement changes for compilation" });
    await expect(changes).toContainText(`reviewed_example · accepted by ${accepted.review?.reviewer ?? ""}`);
    await expect(changes).toContainText(String(accepted.unit));
    const compile = panel.getByRole("button", { name: "Compile reviewed copy", exact: true });
    await expect(compile).toBeDisabled();
    await panel.getByLabel("I reviewed every measurement change for the separate copy").check();
    await compile.click();
    const copyRegion = panel.getByRole("region", { name: "Compiled evidence copy" });
    await expect(copyRegion).toBeVisible();
    await panel.getByRole("region", { name: "Evidence compilation" }).screenshot({ path: testInfo.outputPath("evidence-compilation.png") });
    const bundleFile = await downloaded(page, () => copyRegion.getByRole("button", { name: "Export evidence compilation bundle" }).click());
    const bundle = { path: bundleFile.path, value: bundleFile.value as EvidenceCompilation };
    const compiled = await downloaded(page, () => copyRegion.getByRole("button", { name: "Export compiled project copy" }).click());
    expect(compiled.value).toEqual(bundle.value.project);
    expect(bundle.value.workspace.original_dossier).toEqual(dossier);
    expect(bundle.value.workspace.source_project).toEqual(project);
    expect(bundle.value.workspace.reviews.map(r => [r.claim_id, r.review.status])).toEqual([["unreviewed_example", "rejected"]]);
    const cell = (p: Project) => p.performances.find(m => m.alternative_id === accepted.alternative_id && m.criterion_id === accepted.criterion_id)?.value;
    expect(cell(bundle.value.project)).toBe(accepted.value);
    expect(cell(project)).not.toBe(accepted.value); // the original value is retained in the bundle's source project
    expect((await storedFile(request, project.id)).equals(before)).toBe(true);
    await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
    // The bundle retains the history, so leaving does not require a separate workspace export.
    await page.getByRole("button", { name: "← Projects", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Unsaved changes" })).toHaveCount(0);
    await page.getByLabel("Project file to import", { exact: true }).setInputFiles(compiled.path);
    await page.getByRole("button", { name: "Import as a separate copy", exact: true }).click();
    await expect(page.getByText(/Imported as a separate copy/)).toBeVisible();
    const receiptRegion = page.getByRole("region", { name: "Copy receipt" });
    const receiptFile = await downloaded(page, () => receiptRegion.getByRole("button", { name: "Download copy receipt" }).click());
    const receipt = { path: receiptFile.path, value: receiptFile.value as ProjectCopyReceipt };
    expect(receipt.value.original_fingerprint).toBe(bundle.value.compiled_fingerprint);
    expect(receipt.value.original_project_id).toBe(project.id);
    expect(receipt.value.copy_project_id).not.toBe(project.id);
    expect((await storedFile(request, project.id)).equals(before)).toBe(true);
    // Reopen the bundle in the imported copy: historical only until the receipt is supplied.
    await page.goto(`/#/p/${receipt.value.copy_project_id}`);
    await openTab(page, "Evidence");
    await panel.getByLabel("Evidence dossier or review workspace").setInputFiles(bundle.path);
    const recorded = panel.getByRole("region", { name: "Recorded evidence compilation" });
    await expect(recorded.getByRole("table", { name: "Recorded measurement changes" })).toContainText("reviewed_example");
    const provenance = recorded.getByRole("region", { name: "Evidence compilation provenance" });
    await expect(provenance).toContainText("historical inspection only");
    await expect(panel.getByRole("button", { name: "Review reviewed_example", exact: true })).toBeDisabled();
    await expect(panel.getByText(/Compilation is unavailable/)).toBeVisible();
    await provenance.getByLabel("Copy receipt (optional)").setInputFiles(receipt.path);
    await expect(provenance).toContainText(`Import replaced project ID ${project.id} with ${receipt.value.copy_project_id}`);
    await recorded.screenshot({ path: testInfo.outputPath("verified-copy.png") });
    // In the original project the same bundle is recognised as its source, and review resumes.
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Evidence");
    await panel.getByLabel("Evidence dossier or review workspace").setInputFiles(bundle.path);
    await expect(provenance).toContainText("this artifact's original project");
    await expect(panel.getByRole("button", { name: "Review reviewed_example", exact: true })).toBeEnabled();
    expect((await storedFile(request, project.id)).equals(before)).toBe(true);
  });
}
