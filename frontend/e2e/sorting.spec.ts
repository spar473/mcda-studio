// Value-based sorting in the real application: classes added to a project built from blank, an
// exact class change read in Sensitivity and the class column exported; and the bundled
// supplier qualification example, whose method can be viewed as MAVT without any edit.
import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { AnalysisExportDocumentV2, Project, SortingSensitivityResult } from "../src/api/types";
import { buildTwoOptionModel, openTab, readJson, REPO, saveState, storedFile, tab, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const QUALIFICATION = resolve(REPO, "examples/supplier_qualification/project.json");

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

test("classes added to a project built from blank, an exact class change, and an exported class column", async ({ page, request }, info) => {
  // --- a two-option model from blank: V(A) = 0.6 + 0.2 t and V(B) = 0.9 - 0.5 t in the cost weight t ---
  const id = await buildTwoOptionModel(page, "Sorting acceptance");

  // --- view sorting, add two classes, apply them as one edit ---
  await expect(tab(page, "Classes")).toHaveCount(0);
  await page.getByLabel("Method", { exact: true }).selectOption("mavt_sorting");
  await openTab(page, "Classes");
  await page.getByRole("button", { name: "Add class" }).click();
  await page.getByRole("button", { name: "Add class" }).click();
  await page.getByLabel("Class 1 name").fill("Upper");
  await page.getByLabel("Lower boundary of Upper").fill("0.7");
  await page.getByLabel("Class 2 name").fill("Lower");
  await page.getByRole("button", { name: "Apply classes" }).click();
  await waitIdle(page);
  await expect(page.getByRole("status").filter({ hasText: "No problems with the saved classes." })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const saved = await stored(request, id);
  expect(saved.schema_version).toBe(2);
  expect(saved.sorting?.classes.map((c) => [c.name, c.lower_boundary])).toEqual([["Upper", 0.7], ["Lower", null]]);
  expect(saved.analysis.method).toBe("mavt"); // viewing a method never changes the saved one

  // --- results ---
  await openTab(page, "Results");
  const classes = page.getByRole("table", { name: "Results classes" });
  await expect(classes.locator("tbody tr").nth(0)).toContainText("Alpha");
  await expect(classes.locator("tbody tr").nth(1)).toContainText("Beta");
  await expect(page.getByTestId("class-bands")).toBeVisible();

  // --- sensitivity: the exact weights at which each option changes class, as the engine reports ---
  await openTab(page, "Sensitivity");
  await page.getByLabel("Criterion to vary").selectOption({ label: "Cost" });
  const changes = page.getByRole("table", { name: "Class changes" });
  await expect(changes).toBeVisible();
  const costId = saved.criteria.find((c) => c.name === "Cost")?.id ?? "";
  const engine = await (await request.post("/api/sensitivity", { data: { project: saved, node_id: costId,
    configuration: { ...saved.analysis, method: "mavt_sorting", parameters: {} } } })).json() as SortingSensitivityResult;
  const down = Object.fromEntries(engine.class_changes.map((c) => [c.alternative_id, c.first_change_down]));
  const alpha = saved.alternatives.find((a) => a.name === "Alpha")?.id ?? "", beta = saved.alternatives.find((a) => a.name === "Beta")?.id ?? "";
  expect(down[alpha]?.weight).toBeCloseTo(0.5, 10);
  expect(down[beta]?.weight).toBeCloseTo(0.4, 10);
  await expect(changes.locator("tbody tr").filter({ hasText: "Alpha" })).toContainText(`${(down[alpha]?.weight ?? NaN).toFixed(4)} → Lower`);
  await expect(changes.locator("tbody tr").filter({ hasText: "Beta" })).toContainText(`${(down[beta]?.weight ?? NaN).toFixed(4)} → Upper`);
  const upperId = saved.sorting?.classes.find((c) => c.name === "Upper")?.id ?? "";
  await expect(page.getByTestId(`class-band-${upperId}`)).toBeVisible(); // ids stay stable when renamed

  // --- exports: a version-2 record and the class column ---
  await openTab(page, "Results");
  await page.getByLabel("CSV table", { exact: true }).selectOption("ranking");
  const rows = csvRows(await download(page, info, "Download CSV", "ranking.csv"));
  expect(rows.map((r) => [r.alternative_name, r.class_name, r.export_version])).toEqual([["Alpha", "Upper", "2"], ["Beta", "Lower", "2"]]);
  await page.getByLabel("CSV table", { exact: true }).selectOption("classes");
  const bands = csvRows(await download(page, info, "Download CSV", "classes.csv"));
  expect(bands.map((r) => [r.class_name, r.lower_boundary, r.member_count])).toEqual([["Upper", "0.7", "1"], ["Lower", "", "1"]]);
  const document = JSON.parse(readFileSync(await download(page, info, "Download analysis JSON", "analysis.json"), "utf8")) as AnalysisExportDocumentV2;
  expect([document.export_version, document.record.record_version, document.record.method]).toEqual(["2", "2", "mavt_sorting"]);
});

test("the qualification example opens as sorting, and viewing MAVT edits nothing until it is made the default", async ({ page, request }) => {
  const p = readJson(QUALIFICATION) as Project; p.id = "qualification-browser";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Results");
  await expect(page.getByLabel("Method", { exact: true })).toHaveValue("mavt_sorting");
  const classes = page.getByRole("table", { name: "Results classes" });
  await expect(classes.locator("tbody tr").nth(0)).toContainText("Apex Components, Delta Parts");
  await expect(classes.locator("tbody tr").nth(2)).toContainText("Brightline Supply, Cobalt Industrial");
  await expect(page.getByLabel("Audit sample")).toContainText("Cobalt Industrial");

  await page.getByLabel("Method", { exact: true }).selectOption("mavt");
  await expect(page.getByRole("table", { name: "Ranking" })).toBeVisible();
  await expect(classes).toHaveCount(0);
  await expect(page.getByLabel("Views not offered")).toContainText("does not offer: Classes");
  await expect(tab(page, "Classes")).toBeVisible(); // the project still holds its classes
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);

  await page.getByRole("button", { name: "Use viewed method as saved default" }).click();
  await expect(saveState(page)).toHaveText("● Unsaved changes");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
});
