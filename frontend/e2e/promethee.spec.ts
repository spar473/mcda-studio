// PROMETHEE II in the real application, from a project built from blank: state its own inputs in
// the Outranking tab while the MAVT editors keep their previews, read the flows under their label,
// open the explanation against MAVT, and export a version-2 record and the flows table.
import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import type { AnalysisExportDocumentV2, Project, PrometheeResult } from "../src/api/types";
import { buildTwoOptionModel, openTab, saveState, storedFile, tab, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const LABEL = "net outranking flows: these compare the alternatives with one another and are not preference values";

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
const signed = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(4)}`;

test("outranking inputs on a project built from blank, flows, the explanation against MAVT, and exports", async ({ page, request }, info) => {
  const id = await buildTwoOptionModel(page, "PROMETHEE acceptance");

  // --- view PROMETHEE II; the MAVT editors keep their previews ---
  await expect(tab(page, "Outranking")).toHaveCount(0);
  await page.getByLabel("Method", { exact: true }).selectOption("promethee2");
  await openTab(page, "Weights");
  await expect(page.getByRole("table", { name: "Swing ratings under top level" }).locator("tbody tr").filter({ hasText: "Cost" }))
    .toContainText("0.6667");
  await expect(page.getByText("so the global weight of Quality is 0.3333")).toBeVisible();
  await expect(page.getByText(/does not support/)).toHaveCount(0);

  // --- state PROMETHEE's own inputs: Alpha's 40 NZD cost advantage is capped at p = 10 ---
  await openTab(page, "Outranking");
  await expect(page.getByLabel("Why swing weights are not reused")).toBeVisible();
  const field = (label: string) => page.getByLabel(label, { exact: true });
  await field("Direction for Cost").selectOption("minimise");
  await field("Weight for Cost").fill("1");
  await field("Preference function for Cost").selectOption("v_shape");
  await field("p for Cost").fill("10");
  await field("Direction for Quality").selectOption("maximise");
  await field("Weight for Quality").fill("2");
  await expect(page.getByRole("img", { name: "Function shape for Cost" })).toBeVisible();
  await page.getByRole("button", { name: "Apply outranking inputs" }).click();
  await waitIdle(page);
  await expect(page.getByRole("status").filter({ hasText: "No problems with the saved outranking inputs." })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const saved = await stored(request, id);
  expect(saved.schema_version).toBe(4);
  expect(saved.analysis.method).toBe("mavt"); // viewing a method never changes the saved one
  const name = (criterion: string) => saved.criteria.find((c) => c.id === criterion)?.name;
  expect(saved.promethee?.criteria.map((c) => [name(c.criterion_id), c.direction, c.weight, c.function])).toEqual([
    ["Cost", "minimise", 1, { kind: "v_shape", p: 10 }], ["Quality", "maximise", 2, { kind: "usual" }],
  ]);

  // --- results: the label, the engine's flows on their own axis, PROMETHEE I ---
  await openTab(page, "Results");
  await expect(page.getByLabel("Flow label")).toContainText(`${LABEL[0]?.toUpperCase() ?? ""}${LABEL.slice(1)}.`);
  const engine = await (await request.post("/api/evaluate", { data: { project: saved,
    configuration: { ...saved.analysis, method: "promethee2", parameters: {} } } })).json() as PrometheeResult;
  expect(engine.flows.map((f) => f.name)).toEqual(["Beta", "Alpha"]);
  for (const f of engine.flows) {
    await expect(page.getByRole("table", { name: "Outranking flows" }).locator("tbody tr").filter({ hasText: f.name }))
      .toContainText(`${f.positive_flow.toFixed(4)}${f.negative_flow.toFixed(4)}${signed(f.net_flow)}`);
  }
  await expect(page.getByTestId("flow-bars")).toContainText("net flow (−1 to 1), not a preference value");
  await expect(page.getByRole("table", { name: "Ranking", exact: true })).toHaveCount(0); // no MAVT value view
  await expect(page.getByLabel("Incomparable pairs")).toHaveText("No pair is incomparable.");

  // --- the explanation names the capped criterion and its threshold ---
  await page.getByRole("navigation", { name: "Results views" }).getByRole("button", { name: "Explanation against MAVT" }).click();
  await expect(page.getByRole("table", { name: "Rank comparison" })).toContainText("Beta21");
  const alpha = saved.alternatives.find((a) => a.name === "Alpha")?.id ?? "", beta = saved.alternatives.find((a) => a.name === "Beta")?.id ?? "";
  const pair = page.locator(`li[data-pair="${alpha}|${beta}"]`);
  await expect(pair).toContainText("Flow gap −0.6667 (net flow) = head-to-head −0.6667 + via the other alternatives 0.0000");
  await expect(page.getByRole("list", { name: "Reasons for Alpha and Beta" }))
    .toContainText("Cost: MAVT's advantage for Alpha (+0.267 value) is reduced; Alpha is 40 NZD lower, beyond p = 10, so PROMETHEE counts full preference and no more.");

  // --- exports ---
  await page.getByLabel("CSV table", { exact: true }).selectOption("flows");
  const rows = csvRows(await download(page, info, "Download CSV", "flows.csv"));
  expect(rows.map((r) => [r.alternative_name, r.promethee_rank, r.label])).toEqual([["Beta", "1", LABEL], ["Alpha", "2", LABEL]]);
  expect(new Set(rows.map((r) => r.export_version))).toEqual(new Set(["2"]));
  const document = JSON.parse(readFileSync(await download(page, info, "Download analysis JSON", "analysis.json"), "utf8")) as AnalysisExportDocumentV2;
  expect([document.export_version, document.record.method, document.record.calculation_path]).toEqual(["2", "promethee2", "promethee2.v1"]);
  expect(document.source_project.promethee).toEqual(saved.promethee);
});
