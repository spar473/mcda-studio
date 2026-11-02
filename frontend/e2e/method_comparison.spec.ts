// The method comparison in the real application: a project built from blank in the GUI, given
// every method's section but AHP's, shows AHP's typed error in its column; its link opens the
// Pairwise tab, where judging fixes it. The view then shows every method's own reading, where
// they differ and why, and downloads the long CSV.
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import type { Project } from "../src/api/types";
import { buildTwoOptionModel, openTab, saveState, storedFile, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const CONTEXT = "Agreement between methods that share inputs is not independent validation.";

async function download(page: Page, info: TestInfo, button: string, name: string): Promise<string> {
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: button, exact: true }).click();
  const path = info.outputPath(name); await (await event).saveAs(path);
  return path;
}
function csvRows(path: string): Record<string, string>[] {
  return JSON.parse(execFileSync(PYTHON, ["-c", "import csv,json,sys\nwith open(sys.argv[1],newline='',encoding='utf-8') as f:\n print(json.dumps(list(csv.DictReader(f))))", path], { encoding: "utf8" })) as Record<string, string>[];
}

test("every method side by side, a failing column fixed from its link, reasons and the CSV", async ({ page, request }, info) => {
  const built = await buildTwoOptionModel(page, "Comparison acceptance");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const project = JSON.parse((await storedFile(request, built)).toString()) as Project;
  const id = (name: string) => project.criteria.find((c) => c.name === name)?.id ?? "";

  // --- every section but AHP's, imported as a new project ---
  const stated = { ...project, schema_version: 4, // the sections below need version 4
    sorting: { classes: [{ id: "go", name: "Go", description: "", lower_boundary: 0.5 }, { id: "stop", name: "Stop", description: "", lower_boundary: null }], audit: null },
    smaa: { dependence: "independent", cells: [], groups: [{ parent_id: null, kind: "unknown", intervals: {} }], shared_draws: [] },
    promethee: { criteria: [
      { criterion_id: id("Cost"), direction: "minimise", weight: 1, function: { kind: "usual" } },
      { criterion_id: id("Quality"), direction: "maximise", weight: 2, function: { kind: "usual" } },
    ] } };
  const imported = await request.post("/api/projects/import?on_conflict=new_id", { data: stated });
  expect(imported.status()).toBe(201);
  const newId = ((await imported.json()) as { project: Project }).project.id;
  await page.goto(`/#/p/${newId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Comparison acceptance" })).toBeVisible();

  // --- AHP cannot read the model yet: its column says so, and its link opens the Pairwise tab ---
  await openTab(page, "Compare");
  const table = page.getByRole("table", { name: "Methods side by side" });
  await expect(table.locator("th[data-method]")).toHaveCount(5);
  await expect(table.locator("td[data-method='ahp']").first()).toContainText("Did not run: VALIDATION_FAILED (AHP_NOT_STATED)");
  await page.getByRole("button", { name: "Open pairwise" }).click();
  await expect(page.getByRole("tab", { name: "Pairwise", selected: true })).toBeVisible();
  await page.getByRole("group", { name: "Top-level criteria" }).getByLabel("Judgement of Cost against Quality").selectOption("2");
  await page.getByRole("group", { name: "Alternatives on Cost" }).getByLabel("Judgement of Alpha against Beta").selectOption("3");
  await page.getByRole("group", { name: "Alternatives on Quality" }).getByLabel("Judgement of Alpha against Beta").selectOption("-2");
  await page.getByRole("button", { name: "Apply judgements" }).click();
  await waitIdle(page);

  // --- every method now runs; each column is its own method's reading ---
  await openTab(page, "Compare");
  await expect(table.locator("td.warning")).toHaveCount(0);
  await expect(table.locator("th[data-method='promethee2']")).toContainText("net flow (-1 to 1)");
  await expect(table.locator("th[data-method='ahp']")).toContainText("AHP priority (share of the goal, 0 to 1)");
  await expect(page.getByRole("list", { name: "First place by method" })).toContainText("Alpha: MAVT (additive value), Value-based sorting (MAVT)");
  await expect(page.getByLabel("Why promethee2 differs")).toContainText("PROMETHEE II (outranking flows) puts Beta first where MAVT puts Alpha");
  await expect(page.getByLabel("Comparison context")).toHaveText(CONTEXT);
  const flow = page.getByLabel("PROMETHEE II (outranking flows) net flow for Alpha");
  await expect(flow).toHaveAttribute("min", "-1");

  // --- the long CSV: one row per alternative and method, each naming its own quantity ---
  const rows = csvRows(await download(page, info, "Download comparison CSV", "comparison.csv"));
  expect(rows).toHaveLength(2 * 5);
  expect(new Set(rows.map((r) => `${r.method}:${r.quantity_name}`))).toEqual(new Set([
    "mavt:overall value", "mavt_sorting:overall value", "smaa2:rank-1 acceptability", "promethee2:net flow", "ahp:AHP priority",
  ]));
  expect(new Set(rows.map((r) => r.context))).toEqual(new Set([CONTEXT]));
});
