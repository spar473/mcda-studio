import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { DecisionRecordV2, EvidenceCompilation, EvidenceDossier, EvidenceInspection, ImportedProjectDocument, Project, ProjectDocument } from "../src/api/types";
import { openTab, readJson, REPO, storedFile } from "./helpers";

/** Review, compile and import a separate copy through the production HTTP endpoints. */
async function compiledCopy(request: APIRequestContext, example: string, name: string) {
  const dossier = readJson(resolve(REPO, `examples/evidence_demo/${name}.json`)) as EvidenceDossier;
  const raw = readJson(resolve(REPO, `examples/${example}/project.json`)) as Project;
  expect([201, 409]).toContain((await request.post("/api/projects/import", { data: raw })).status());
  const original = await (await request.get(`/api/projects/${raw.id}`)).json() as ProjectDocument;
  expect(original.fingerprint).toBe(dossier.project_fingerprint); // the exact paired project
  const inspected = await (await request.post("/api/evidence/inspect", { data: { project: original.project, document: dossier } })).json() as EvidenceInspection;
  const reviewed = await (await request.post("/api/evidence/review", { data: { project: original.project, workspace: inspected.workspace,
    expected_review_digest: inspected.preview.review_digest,
    event: { claim_id: "unreviewed_example", review: { status: "rejected", reviewer: "Demonstration reviewer", reviewed_at: "2026-11-01T00:00:00Z" } } } })).json() as EvidenceInspection;
  const compiled = await request.post("/api/evidence/compile", { data: { project: original.project, workspace: reviewed.workspace,
    expected_review_digest: reviewed.preview.review_digest, expected_workspace_digest: reviewed.workspace.digest } });
  expect(compiled.status()).toBe(200);
  const bundle = await compiled.json() as EvidenceCompilation;
  const imported = await (await request.post("/api/projects/import?on_conflict=new_id", { data: bundle.project })).json() as ImportedProjectDocument;
  if (!imported.copy_receipt) throw Error("Separate copy has no receipt");
  return { original, bundle, copy: imported.project, receipt: imported.copy_receipt };
}

async function exportRecord(page: Page, path: string): Promise<DecisionRecordV2> {
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export decision record", exact: true }).click();
  const downloaded = await (await event).path();
  if (!downloaded) throw Error("Record download missing");
  const text = readFileSync(downloaded, "utf8");
  writeFileSync(path, text);
  return JSON.parse(text) as DecisionRecordV2;
}

for (const [name, example, chosenId] of [["vc", "nz_deeptech_vc", "hyades"], ["supplier", "supplier_qualification", "apex"]] as const) {
  test(`${name} decision is recorded on a verified copy, reopened and revised without changing earlier files`, async ({ page, request }, testInfo) => {
    const { original, bundle, copy, receipt } = await compiledCopy(request, example, name);
    const chosen = copy.alternatives.find(a => a.id === chosenId)?.name ?? chosenId;
    const bundlePath = testInfo.outputPath("evidence-compilation.json"); writeFileSync(bundlePath, JSON.stringify(bundle));
    const receiptPath = testInfo.outputPath("copy-receipt.json"); writeFileSync(receiptPath, JSON.stringify(receipt));
    const originalBytes = await storedFile(request, original.project.id);
    const copyBytes = await storedFile(request, copy.id);
    await page.goto(`/#/p/${copy.id}`);
    await openTab(page, "Decision");
    const panel = page.getByRole("region", { name: "Decision records", exact: true });
    await panel.getByLabel("Decision owner").fill("Demonstration owner");
    await panel.getByLabel("Selected alternative").selectOption(chosenId);
    await panel.getByLabel("Rationale").fill("Synthetic illustration of a recorded choice; not a recommendation.");
    await panel.getByLabel("Unresolved assumptions (one per line)").fill("The conflicting synthetic claim stays rejected");
    await panel.getByLabel("Review triggers (one per line)").fill("A new source is reviewed");
    await panel.getByRole("button", { name: "Add analysis" }).click();
    await panel.getByLabel("Analysis 2 method").selectOption("smaa2");
    await panel.getByLabel("Supporting bundles and copy receipts").setInputFiles([bundlePath, receiptPath]);
    await expect(panel.getByLabel("Supporting files")).toContainText("bundle with copy receipt");
    await panel.getByRole("button", { name: "Preview decision record" }).click();
    const previewed = panel.getByLabel("Previewed record", { exact: true });
    await expect(previewed).toContainText(`Selected: ${chosen}`);
    await expect(panel.getByLabel("Previewed record artifacts")).toContainText("receipt-verified copy");
    await expect(panel.getByLabel("Previewed record measurement provenance")).toContainText("claim reviewed_example");
    await expect(panel.getByLabel("Previewed record analyses")).toContainText("smaa2");
    await previewed.screenshot({ path: testInfo.outputPath("decision-record.png") });
    // An unexported record is protected like unexported reviews.
    await page.getByRole("button", { name: "← Projects", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Unsaved changes" })).toBeVisible();
    await page.getByRole("dialog", { name: "Unsaved changes" }).getByRole("button", { name: "Keep editing", exact: true }).click();
    const firstPath = testInfo.outputPath("decision-1.json");
    const first = await exportRecord(page, firstPath);
    const firstBytes = readFileSync(firstPath);
    expect(first.project_fingerprint).toBe((await (await request.get(`/api/projects/${copy.id}`)).json() as ProjectDocument).fingerprint);
    expect(first.anchors.map(a => [a.relationship, a.artifact_digest])).toEqual([["verified_copy", bundle.digest]]);
    expect(first.analyses.map(a => a.configuration.method)).toContain("smaa2");
    // Reopen in a fresh page, change an assumption and create a linked revision.
    await page.reload(); await openTab(page, "Decision");
    await panel.getByLabel("Decision record file").setInputFiles(firstPath);
    const opened = panel.getByLabel("Opened decision record");
    await expect(opened).toContainText("records exactly the current project");
    await opened.getByRole("button", { name: "Revise this record" }).click();
    await expect(panel.getByText(/Revising decision-1.json/)).toBeVisible();
    await panel.getByLabel("Unresolved assumptions (one per line)").fill("The conflicting claim needs a second source");
    await panel.getByRole("button", { name: "Preview decision record" }).click();
    await expect(panel.getByLabel("Previewed record", { exact: true })).toContainText("Revises record");
    const second = await exportRecord(page, testInfo.outputPath("decision-2.json"));
    expect(second.previous_digest).toBe(first.digest);
    expect(second.decision.unresolved_assumptions).toEqual(["The conflicting claim needs a second source"]);
    expect(second.supporting_artifacts).toEqual(first.supporting_artifacts);
    await panel.getByLabel("Decision record file").setInputFiles(testInfo.outputPath("decision-2.json"));
    await panel.getByLabel("Its predecessor record (optional)").setInputFiles(firstPath);
    await expect(panel.getByLabel("Opened decision record")).toContainText("The selected predecessor is the record it revises");
    // Earlier artifacts and projects are untouched.
    expect(readFileSync(firstPath).equals(firstBytes)).toBe(true);
    expect((await storedFile(request, original.project.id)).equals(originalBytes)).toBe(true);
    expect((await storedFile(request, copy.id)).equals(copyBytes)).toBe(true);
    await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  });
}
