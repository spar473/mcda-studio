import { expect, test, type Locator, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { openTab, readJson, REPO, saveState, storedFile } from "./helpers";
import type { CalculationWorkspace, DerivedCompilation, DerivedPreview, Project } from "../src/api/types";

async function openCalculations(page: Page): Promise<Locator> {
  await openTab(page, "Measurements");
  const panel = page.getByLabel("Calculated measurements preview", { exact: true });
  if (!await panel.evaluate(element => (element as HTMLDetailsElement).open)) await page.getByText("Calculated measurements", { exact: true }).click();
  return panel;
}

async function downloaded(page: Page, click: () => Promise<void>): Promise<string> {
  const event = page.waitForEvent("download");
  await click();
  const path = await (await event).path();
  if (!path) throw Error("download missing");
  return path;
}

test("edit a shared-model factor, review, apply as one undoable edit, rank, save and reproduce", async ({ page, request }, testInfo) => {
  const project = readJson(resolve(REPO, "examples/derived_measurements/venture-project.json")) as Project;
  project.id = "calculation-workspace-venture";
  const imported = await request.post("/api/projects/import", { data: project });
  expect(imported.status()).toBe(201);
  const model = readJson(resolve(REPO, "examples/derived_measurements/venture-model.json")) as DerivedPreview["model"];
  model.project_fingerprint = (await imported.json() as { fingerprint: string }).fingerprint;
  const before = await storedFile(request, project.id);
  await page.goto(`/#/p/${project.id}`);
  let panel = await openCalculations(page);
  await panel.getByLabel("Calculation model", { exact: true }).setInputFiles({ name: "venture-model.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(model)) });
  await expect(panel.getByText(/Bound to this project revision · 0 recorded changes/)).toBeVisible();
  await panel.getByText("Source inputs and review", { exact: true }).click();
  await expect(panel.getByRole("button", { name: "Revise adoption_a" })).toBeDisabled();
  await panel.getByLabel("Your name (recorded with each change)").fill("Analyst");
  const changes = panel.getByRole("region", { name: "Measurement changes" });
  await expect(changes).toContainText("missing");
  await panel.getByLabel("I reviewed every measurement change to apply").check();
  await panel.getByRole("button", { name: "Apply to this project" }).click();
  await expect(panel.getByRole("region", { name: "Applied calculation" })).toBeVisible();
  await expect(saveState(page)).toHaveText("● Unsaved changes");
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);

  // Revising a shared-model factor leaves it pending: no calculated value can be applied.
  await expect(panel.getByLabel("Calculation source inputs")).toContainText("Used by market_a, market_b for Option A, Option B. Shared across alternatives");
  await panel.getByRole("button", { name: "Revise adoption_a" }).click();
  const form = panel.getByRole("form", { name: "Revise factor adoption_a" });
  await form.getByLabel("Value", { exact: true }).fill("0.07");
  await form.getByRole("button", { name: "Record factor definition" }).click();
  await expect(panel.getByRole("alert").filter({ hasText: "DERIVED_UNREVIEWED_SOURCE" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Apply to this project" })).toHaveCount(0);
  await panel.getByRole("button", { name: "Review adoption_a" }).click();
  await panel.getByRole("form", { name: "Review factor adoption_a" }).getByRole("button", { name: "Record review" }).click();
  await expect(changes.getByRole("row", { name: /Option A/ })).toContainText("600,000840,000Would change");
  await expect(changes.getByRole("row", { name: /Option B/ })).toContainText("Unchanged");
  await panel.getByText("Dependency graph for market_a", { exact: true }).click();
  await expect(panel.getByText("Factor adoption_a = 0.07 (dimensionless) (accepted by Analyst)")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Apply to this project" })).toBeDisabled();
  await panel.getByLabel("I reviewed every measurement change to apply").check();
  await panel.getByRole("button", { name: "Apply to this project" }).click();
  await expect(panel.getByText(/Bound to this project revision · 4 recorded changes · 2 applications/)).toBeVisible();
  await panel.screenshot({ path: testInfo.outputPath("calculation-workspace.png") });

  await openTab(page, "Results");
  await expect(page.getByRole("table", { name: "Ranking", exact: true }).locator("tbody tr").first()).toContainText("Option A");

  // One application is one undo step; the workspace recognises the earlier revision, then Redo.
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  panel = await openCalculations(page);
  await expect(panel.getByRole("alert").filter({ hasText: "earlier revision" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Revise adoption_a" })).toBeDisabled();
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(panel.getByText(/Bound to this project revision · 4 recorded changes/)).toBeVisible();

  // Save stores the project only; unexported calculation history is guarded first.
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(panel.getByText(/Calculation changes have not been exported/)).toBeVisible();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
  const workspacePath = await downloaded(page, () => panel.getByRole("button", { name: "Export calculation workspace" }).click());
  const bundlePath = await downloaded(page, () => panel.getByRole("button", { name: "Export calculation bundle for this application" }).click());
  await expect(panel.getByText(/Calculation changes have not been exported/)).toHaveCount(0);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const stored = await (await request.get(`/api/projects/${project.id}`)).json() as { fingerprint: string; project: Project };
  const bundle = JSON.parse(readFileSync(bundlePath, "utf8")) as DerivedCompilation;
  expect(bundle.compiled_fingerprint).toBe(stored.fingerprint);
  expect(stored.project).toEqual(bundle.project);
  const binding = await request.post("/api/provenance/binding", { data: { project: stored.project, artifact: bundle } });
  expect((await binding.json() as { relationship: string }).relationship).toBe("compiled");
  const workspace = JSON.parse(readFileSync(workspacePath, "utf8")) as CalculationWorkspace;
  expect(workspace.events.map(e => e.kind)).toEqual(["apply", "source", "review", "apply"]);

  // Reopen in a fresh page: the workspace replays and reproduces the saved measurements.
  await page.reload();
  panel = await openCalculations(page);
  await panel.getByLabel("Calculation model", { exact: true }).setInputFiles(workspacePath);
  await expect(panel.getByText(/Bound to this project revision · 4 recorded changes/)).toBeVisible();
  await expect(changes.getByText("Would change")).toHaveCount(0);
  await expect(panel.getByLabel("Calculated measurements", { exact: true })).toContainText("840,000");
  await panel.getByText(/Calculation history/).click();
  await expect(panel.getByLabel("Calculation history")).toContainText("Analyst accepted factor adoption_a");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});

test("author a formula from blank, see dimensional errors explained, and record a tool proposal", async ({ page, request }) => {
  const project = readJson(resolve(REPO, "examples/derived_measurements/supplier-project.json")) as Project;
  project.id = "calculation-workspace-blank";
  expect((await request.post("/api/projects/import", { data: project })).status()).toBe(201);
  const before = await storedFile(request, project.id);
  await page.goto(`/#/p/${project.id}`);
  const panel = await openCalculations(page);
  await panel.getByRole("button", { name: "Start a new calculation model" }).click();
  await panel.getByLabel("Your name (recorded with each change)").fill("Analyst");
  await panel.getByText("Declared unit dimensions", { exact: true }).click();
  await panel.getByRole("button", { name: "Add unit" }).click();
  const unit = panel.getByRole("form", { name: "New unit" });
  await unit.getByLabel("Unit name").fill("NZD");
  await unit.getByLabel("Base dimensions").fill("NZD");
  await unit.getByRole("button", { name: "Record unit" }).click();
  await expect(panel.getByLabel("Declared unit dimensions")).toContainText("NZD: NZD.");

  await panel.getByText("Source inputs and review", { exact: true }).click();
  for (const [id, value, unitName, tool] of [["price_a", "40", "NZD", false], ["annual_units", "1000", "1", true]] as const) {
    await panel.getByRole("button", { name: "Add source factor" }).click();
    const form = panel.getByRole("form", { name: "New source factor" });
    await form.getByLabel("Factor ID (used in formulas)").fill(id);
    await form.getByLabel("Value", { exact: true }).fill(value);
    await form.getByLabel("Unit").selectOption(unitName);
    await form.getByLabel("Source name").fill("Synthetic quotation");
    await form.getByLabel("Source reference").fill("local:quote-1");
    await form.getByLabel("Source description").fill("Invented for testing");
    if (tool) {
      await form.getByLabel("Proposed by").selectOption("tool");
      await form.getByLabel("Tool ID").fill("synthetic-extractor");
      await form.getByLabel("Tool version").fill("0.1");
    }
    await form.getByRole("button", { name: "Record factor definition" }).click();
    await panel.getByRole("button", { name: `Review ${id}` }).click();
    await panel.getByRole("form", { name: `Review factor ${id}` }).getByRole("button", { name: "Record review" }).click();
    await expect(panel.getByLabel("Calculation source inputs")).toContainText(`${id}: recorded ${value === "1000" ? "1,000" : value} ${unitName === "1" ? "(dimensionless)" : unitName}; review accepted`);
  }
  await expect(panel.getByLabel("Calculation source inputs")).toContainText("Proposed by Analyst (tool proposal), tool synthetic-extractor 0.1");

  await panel.getByText("Formula definitions and review", { exact: true }).click();
  await panel.getByRole("button", { name: "Add formula" }).click();
  let formula = panel.getByRole("form", { name: "New formula" });
  await formula.getByLabel("Formula ID").fill("tco_a");
  await formula.getByLabel("Expression").fill("price_a * annual_units + 5");
  await formula.getByLabel("Result unit").selectOption("NZD");
  await formula.getByLabel("Target measurement").selectOption({ label: "Option A / Three-year total cost of ownership (NZD)" });
  await formula.getByRole("button", { name: "Record formula definition" }).click();
  await expect(panel.getByLabel("Check for tco_a")).toHaveText("Check failed: Only quantities with the same dimensions can be added, subtracted or compared: NZD and dimensionless.");
  await panel.getByRole("button", { name: "Review tco_a" }).click();
  await panel.getByRole("form", { name: "Review formula tco_a" }).getByRole("button", { name: "Record review" }).click();
  await expect(panel.getByRole("alert").filter({ hasText: "CALCULATION_ACCEPT_INVALID" })).toBeVisible();
  await panel.getByRole("form", { name: "Review formula tco_a" }).getByRole("button", { name: "Cancel" }).click();
  await panel.getByRole("button", { name: "Edit tco_a" }).click();
  formula = panel.getByRole("form", { name: "Edit formula tco_a" });
  await formula.getByLabel("Expression").fill("price_a * annual_units");
  await formula.getByRole("button", { name: "Record formula definition" }).click();
  await expect(panel.getByLabel("Check for tco_a")).toHaveText("Check: Calculates 40000 NZD; its dimensions (NZD) match the declared unit.");
  await panel.getByRole("button", { name: "Review tco_a" }).click();
  await panel.getByRole("form", { name: "Review formula tco_a" }).getByRole("button", { name: "Record review" }).click();
  await expect(panel.getByRole("region", { name: "Measurement changes" })).toContainText("Option AThree-year total cost of ownershipmissing40,000Would change");
  await expect(panel.getByRole("alert")).toHaveCount(0);
  // Nothing so far changed the project: authoring and review are workspace events only.
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
  // Leaving with unexported calculation history asks first.
  await page.getByRole("button", { name: "← Projects", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Unsaved changes" })).toBeVisible();
});
