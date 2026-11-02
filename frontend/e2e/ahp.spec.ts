// AHP in the real application, from a project built from blank: enter the pairwise matrices, see a
// consistency warning with its triad and fix it, read the priorities under their label, save,
// reopen, and export a version-2 record and the priorities table.
import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import type { AhpResult, AnalysisExportDocumentV2, Project } from "../src/api/types";
import { addTopLevel, buildTwoOptionModel, openTab, saveState, storedFile, tab, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const LABEL = "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT values or swing weights";

async function download(page: Page, info: TestInfo, button: string, name: string): Promise<string> {
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: button, exact: true }).click();
  const path = info.outputPath(name); await (await event).saveAs(path);
  return path;
}
function csvRows(path: string): Record<string, string>[] {
  return JSON.parse(execFileSync(PYTHON, ["-c", "import csv,json,sys\nwith open(sys.argv[1],newline='',encoding='utf-8') as f:\n print(json.dumps(list(csv.DictReader(f))))", path], { encoding: "utf8" })) as Record<string, string>[];
}
async function stored(request: APIRequestContext, id: string): Promise<Project> {
  return JSON.parse((await storedFile(request, id)).toString()) as Project;
}

test("pairwise matrices on a project built from blank, a consistency warning fixed, priorities, reopen and exports", async ({ page, request }, info) => {
  const id = await buildTwoOptionModel(page, "AHP acceptance");
  await addTopLevel(page, "Delivery"); // a third criterion, so the top-level matrix has a triad
  await waitIdle(page);

  // --- view AHP and judge every matrix; the top level is cyclic at first ---
  await expect(tab(page, "Pairwise")).toHaveCount(0);
  await page.getByLabel("Method", { exact: true }).selectOption("ahp");
  await expect(page.getByLabel("AHP reads no profile or scenario")).toBeVisible();
  await openTab(page, "Pairwise");
  const top = page.getByRole("group", { name: "Top-level criteria" });
  await top.getByLabel("Judgement of Cost against Quality").selectOption("2");
  await top.getByLabel("Judgement of Quality against Delivery").selectOption("2");
  await top.getByLabel("Judgement of Cost against Delivery").selectOption("-4"); // Delivery over Cost: cyclic
  for (const [leaf, value] of [["Cost", "3"], ["Quality", "-2"], ["Delivery", "1"]] as const) {
    await page.getByRole("group", { name: `Alternatives on ${leaf}` }).getByLabel("Judgement of Alpha against Beta").selectOption(value);
  }
  const warning = top.getByLabel("Consistency warning: Top-level criteria");
  await expect(warning).toContainText("is above 0.10: review the judgements. Most inconsistent triad: Cost over Quality: 2; Quality over Delivery: 2; Cost over Delivery: 1/4, where consistency would need 4.");
  await expect(top.locator('tr[data-in-triad="true"]')).toHaveCount(3);

  // --- fix the warning: Cost over Delivery, 4 times, is consistent ---
  await top.getByLabel("Judgement of Cost against Delivery").selectOption("4");
  await expect(warning).toHaveCount(0);
  await expect(top.getByLabel("Consistency: Top-level criteria")).toContainText("CR 0.0000");
  await page.getByRole("button", { name: "Apply judgements" }).click();
  await waitIdle(page);
  await expect(page.getByRole("status").filter({ hasText: "No problems with the saved judgements." })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const saved = await stored(request, id);
  expect(saved.schema_version).toBe(5);
  expect(saved.analysis.method).toBe("mavt"); // viewing a method never changes the saved one
  const name = (criterion: string) => saved.criteria.find((c) => c.id === criterion)?.name;
  expect(saved.ahp?.criteria[0]?.judgements.map((j) => [name(j.row), name(j.column), j.value])).toEqual([
    ["Cost", "Quality", 2], ["Cost", "Delivery", 4], ["Quality", "Delivery", 2],
  ]);

  // --- results: the label and the engine's priorities ---
  await openTab(page, "Results");
  await expect(page.getByLabel("AHP label")).toContainText(`${LABEL}.`);
  const engine = await (await request.post("/api/evaluate", { data: { project: saved,
    configuration: { ...saved.analysis, method: "ahp", parameters: {} } } })).json() as AhpResult;
  expect(engine.matrices.every((m) => !m.inconsistent)).toBe(true);
  for (const a of engine.alternatives) {
    await expect(page.getByRole("table", { name: "AHP priorities" }).locator("tbody tr").filter({ hasText: a.name }))
      .toContainText(`${String(a.rank)}${a.name} ${a.alternative_id}${a.priority.toFixed(4)}`);
  }
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toHaveCount(0); // no MAVT value view
  await expect(page.getByRole("table", { name: "AHP consistency" })).not.toContainText("above 0.10");

  // --- exports ---
  await page.getByLabel("CSV table", { exact: true }).selectOption("priorities");
  const rows = csvRows(await download(page, info, "Download CSV", "priorities.csv"));
  expect(rows.map((r) => [r.alternative_name, r.ahp_rank, r.label])).toEqual(
    engine.alternatives.map((a) => [a.name, String(a.rank), LABEL]));
  const document = JSON.parse(readFileSync(await download(page, info, "Download analysis JSON", "analysis.json"), "utf8")) as AnalysisExportDocumentV2;
  expect([document.export_version, document.record.method, document.record.calculation_path]).toEqual(["2", "ahp", "ahp.eigen_power.v1"]);
  expect(document.source_project.ahp).toEqual(saved.ahp);

  // --- reopen: the judgements come back from the saved file ---
  await page.reload();
  await openTab(page, "Pairwise");
  await expect(page.getByRole("group", { name: "Top-level criteria" }).getByLabel("Judgement of Cost against Delivery")).toHaveValue("4");
  await expect(page.getByRole("group", { name: "Alternatives on Quality" }).getByLabel("Judgement of Alpha against Beta")).toHaveValue("-2");
});
