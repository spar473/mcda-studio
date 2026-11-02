// The feasibility check in the real application: a project built from blank in the GUI is given
// two requirements in the Requirements tab, whose live result is computed in Python. Alpha passes,
// Beta fails the cost cap, and the ranking stays complete and unchanged with feasibility beside it
// in Results and the comparison. The CSV downloads one row per alternative and requirement. A
// cleared measurement is unknown, never a failure.
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "node:child_process";
import type { Project } from "../src/api/types";
import { buildTwoOptionModel, openTab, readRanking, saveState, storedFile, waitIdle } from "./helpers";

const PYTHON = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const LABEL = "feasibility: each requirement is tested on its own measurement; no score offsets a failure";

async function download(page: Page, info: TestInfo, button: string, name: string): Promise<string> {
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: button, exact: true }).click();
  const path = info.outputPath(name); await (await event).saveAs(path);
  return path;
}
function csvRows(path: string): Record<string, string>[] {
  return JSON.parse(execFileSync(PYTHON, ["-c", "import csv,json,sys\nwith open(sys.argv[1],newline='',encoding='utf-8') as f:\n print(json.dumps(list(csv.DictReader(f))))", path], { encoding: "utf8" })) as Record<string, string>[];
}
const overall = (page: Page, scope: string, alternative: string) =>
  page.getByRole("region", { name: scope }).getByRole("table", { name: "Feasibility by alternative" })
    .getByRole("row", { name: new RegExp(`^${alternative}`) }).locator("td").first();

test("requirements from blank: pass, fail and unknown beside an unchanged ranking, and the CSV", async ({ page, request }, info) => {
  const id = await buildTwoOptionModel(page, "Feasibility acceptance");
  await openTab(page, "Results");
  const before = await readRanking(page);
  expect(before.map((r) => r.name)).toEqual(["Alpha", "Beta"]);

  // --- two requirements, checked live as they are drafted ---
  await openTab(page, "Requirements");
  const editor = page.getByRole("region", { name: "Requirements" });
  await editor.getByLabel("New requirement criterion").selectOption({ label: "Cost" });
  await editor.getByRole("button", { name: "Add requirement" }).click();
  await expect(editor.getByLabel("Unit of Cost requirement")).toHaveValue("NZD");
  await editor.getByLabel("Name of cost").fill("Cost cap");
  await editor.getByLabel("Maximum of Cost cap", { exact: true }).fill("50");
  await editor.getByLabel("New requirement criterion").selectOption({ label: "Quality" });
  await editor.getByRole("button", { name: "Add requirement" }).click();
  await editor.getByLabel("Name of quality").fill("Quality floor");
  await editor.getByLabel("Minimum of Quality floor", { exact: true }).fill("6"); // Alpha's own value: the limit itself passes
  const draft = editor.getByRole("table", { name: "Feasibility by alternative" });
  await expect(draft.getByRole("row", { name: /^Alpha/ }).locator("td").first()).toHaveText("passes");
  await expect(draft.getByRole("row", { name: /^Beta/ }).locator("td").first()).toHaveText("fails");
  await expect(draft.getByRole("row", { name: /^Beta/ })).toContainText("60 NZD is above the maximum 50 NZD");
  await editor.getByRole("button", { name: "Apply requirements" }).click();
  await waitIdle(page);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const stored = JSON.parse((await storedFile(request, id)).toString()) as Project;
  expect(stored.schema_version).toBe(6);
  expect(stored.requirements?.map((r) => r.name)).toEqual(["Cost cap", "Quality floor"]);

  // --- Results: the same complete ranking, feasibility beside it ---
  await openTab(page, "Results");
  expect(await readRanking(page)).toEqual(before);
  await expect(overall(page, "Feasibility beside the ranking", "Beta")).toHaveText("fails");
  await expect(overall(page, "Feasibility beside the ranking", "Alpha")).toHaveText("passes");
  await expect(page.getByLabel("Feasibility label")).toContainText("It does not change any ranking.");
  const rows = csvRows(await download(page, info, "Download feasibility CSV", "feasibility.csv"));
  expect(rows.map((r) => [r.alternative_name, r.requirement_name, r.status, r.overall_status])).toEqual([
    ["Alpha", "Cost cap", "pass", "pass"], ["Alpha", "Quality floor", "pass", "pass"],
    ["Beta", "Cost cap", "fail", "fail"], ["Beta", "Quality floor", "pass", "fail"],
  ]);
  expect(new Set(rows.map((r) => r.label))).toEqual(new Set([LABEL]));

  // --- the comparison keeps every row, with each status in its own column ---
  await page.route("**/api/feasibility", route => route.abort("failed"));
  await openTab(page, "Compare");
  await expect(page.getByRole("alert").filter({ hasText: "Feasibility could not be checked" })).toBeVisible();
  await page.unroute("**/api/feasibility");
  await page.getByRole("button", { name: "Retry feasibility" }).click();
  const table = page.getByRole("table", { name: "Methods side by side" });
  await expect(table.locator("tbody tr")).toHaveCount(2);
  await expect(table.locator("tr[data-alternative-id] [data-feasibility='fail']")).toHaveText("fails (Cost cap)");
  await expect(table.locator("tr[data-alternative-id] [data-feasibility='pass']")).toHaveText("passes");

  // --- a cleared measurement is unknown, not a failure ---
  await openTab(page, "Measurements");
  const cell = page.getByLabel("Alpha on Quality", { exact: true });
  await cell.fill("");
  await cell.press("Enter");
  await waitIdle(page);
  await openTab(page, "Requirements");
  await expect(draft.getByRole("row", { name: /^Alpha/ }).locator("td").first()).toHaveText("unknown");
  await expect(draft.getByRole("row", { name: /^Alpha/ })).toContainText("no measurement");
  await expect(draft.getByRole("row", { name: /^Beta/ }).locator("td").first()).toHaveText("fails");
});
