// SMAA-2 in the real application, from a project built from blank: state a measurement range and
// unknown weights, view acceptabilities with their intervals and label, try another run without
// editing anything, and export a version-2 record and the rank-acceptability table.
import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import type { AnalysisExportDocumentV2, Project, SmaaResult } from "../src/api/types";
import { buildTwoOptionModel, openTab, saveState, storedFile, tab, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");

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
const percent = (value: number) => `${(value * 100).toFixed(1)} %`;

test("stated uncertainty on a project built from blank, acceptabilities with intervals, and exports", async ({ page, request }, info) => {
  const id = await buildTwoOptionModel(page, "SMAA acceptance");

  // --- view SMAA-2, state a range for Alpha's cost and unknown top-level weights ---
  await expect(tab(page, "Uncertainty")).toHaveCount(0);
  await page.getByLabel("Method", { exact: true }).selectOption("smaa2");
  await openTab(page, "Uncertainty");
  await page.getByRole("button", { name: "Add distribution" }).click();
  await page.getByLabel("Lower for Alpha on Cost").fill("10");
  await page.getByLabel("Upper for Alpha on Cost").fill("30");
  await page.getByLabel("Weight uncertainty under Top level").selectOption("unknown");
  await page.getByRole("button", { name: "Apply uncertainty" }).click();
  await waitIdle(page);
  await expect(page.getByRole("status").filter({ hasText: "No problems with the saved uncertainty." })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const saved = await stored(request, id);
  expect(saved.schema_version).toBe(3);
  expect(saved.analysis.method).toBe("mavt"); // viewing a method never changes the saved one

  // --- results: the label, the provenance and the engine's numbers ---
  await openTab(page, "Results");
  await expect(page.getByLabel("Acceptability label")).toContainText("Sampled acceptability under these assumptions.");
  await expect(page.getByLabel("Acceptability provenance")).toContainText("10000 draws, seed 0");
  const engine = await (await request.post("/api/evaluate", { data: { project: saved,
    configuration: { ...saved.analysis, method: "smaa2", parameters: {} } } })).json() as SmaaResult;
  const alpha = engine.acceptability.find((a) => a.name === "Alpha");
  expect(alpha?.ranks[0]?.lower).not.toBeNull();
  const first = alpha?.ranks[0];
  await expect(page.getByRole("table", { name: "Rank acceptability" }).locator("tbody tr").filter({ hasText: "Alpha" }))
    .toContainText(`${percent(first?.frequency ?? NaN)} (${percent(first?.lower ?? NaN)}–${percent(first?.upper ?? NaN)})`);
  await expect(page.getByRole("list", { name: "Inputs to check" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Ranking" })).toHaveCount(0); // no MAVT score view

  // --- another run is a view: weights only, with nothing edited ---
  await page.getByLabel("Uncertain inputs").selectOption("preference");
  await expect(page.getByLabel("Acceptability provenance")).toContainText("preference run");
  await expect(saveState(page)).toHaveText("All changes saved");

  // --- exports ---
  await page.getByLabel("CSV table", { exact: true }).selectOption("rank_acceptability");
  const rows = csvRows(await download(page, info, "Download CSV", "rank_acceptability.csv"));
  expect(rows).toHaveLength(2 * (2 + 2));
  expect(new Set(rows.map((r) => r.method))).toEqual(new Set(["smaa2"]));
  expect(new Set(rows.map((r) => r.export_version))).toEqual(new Set(["2"]));
  const document = JSON.parse(readFileSync(await download(page, info, "Download analysis JSON", "analysis.json"), "utf8")) as AnalysisExportDocumentV2;
  expect([document.export_version, document.record.method]).toEqual(["2", "smaa2"]);
  expect(document.record.method === "smaa2" ? document.record.result.run : null).toBe("preference");
});
