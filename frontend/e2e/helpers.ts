import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const REPO = resolve(import.meta.dirname, "..", "..");
export const STORE = resolve(import.meta.dirname, "..", ".e2e-store");
export const VC_FILE = resolve(REPO, "examples", "nz_deeptech_vc", "project.json");

export function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

/** The element at ``index``; a missing one is a test-setup error, not a silent undefined. */
export function at<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`expected an item at index ${String(index)}`);
  return item;
}

/** The engine, run in a separate process on a saved file (the CLI). */
export function cliEvaluate(file: string, scenario?: string): Record<string, unknown> {
  const python = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
  const args = ["-m", "mcda_studio", "evaluate", file, "--json"];
  if (scenario) args.push("--scenario", scenario);
  return JSON.parse(execFileSync(python, args, { cwd: REPO, encoding: "utf8" })) as Record<string, unknown>;
}

export async function storedFile(request: APIRequestContext, id: string): Promise<Buffer> {
  const r = await request.get(`/api/projects/${id}/file`);
  expect(r.ok()).toBeTruthy();
  return r.body();
}

export const tab = (page: Page, name: string): Locator => page.getByRole("tab", { name });

export async function openTab(page: Page, name: string): Promise<void> {
  await tab(page, name).click();
  await expect(tab(page, name)).toHaveAttribute("aria-selected", "true");
}

export const saveState = (page: Page): Locator => page.getByTestId("save-state");

/** The label button of a tree row, matched by the item's name. */
export const treeItem = (page: Page, name: string): Locator =>
  page.locator(".tree-label").filter({ has: page.locator(".tree-name", { hasText: new RegExp(`^${name}$`) }) });

export async function selectNode(page: Page, name: string): Promise<void> {
  await openTab(page, "Model");
  await treeItem(page, name).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(name);
}

async function renameSelected(page: Page, name: string): Promise<void> {
  const field = page.getByLabel("Name", { exact: true });
  await field.fill(name);
  await field.press("Enter");
  await expect(treeItem(page, name)).toBeVisible();
}

export async function addTopLevel(page: Page, name: string): Promise<void> {
  await openTab(page, "Model");
  await page.getByRole("button", { name: "Add top-level objective" }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("New criterion");
  await renameSelected(page, name);
}

export async function addChild(page: Page, parent: string, name: string): Promise<void> {
  await selectNode(page, parent);
  await page.getByRole("button", { name: "Add child" }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("New criterion");
  await renameSelected(page, name);
}

export async function setNumeric(
  page: Page,
  o: { type: "Ratio" | "Interval"; unit: string; lower: number; upper: number; lowerIsBetter?: boolean },
): Promise<void> {
  await page.getByLabel("Measurement type").selectOption({ label: o.type === "Ratio" ? "Ratio (numeric, true zero)" : "Interval (numeric, arbitrary zero)" });
  await expect(page.getByLabel("Preference function")).toBeVisible();
  const unit = page.getByLabel("Unit", { exact: true });
  await unit.fill(o.unit);
  await unit.press("Enter");
  const lower = page.getByLabel("Lower bound", { exact: true });
  await lower.fill(String(o.lower));
  await lower.press("Enter");
  const upper = page.getByLabel("Upper bound", { exact: true });
  await upper.fill(String(o.upper));
  await upper.press("Enter");
  if (o.lowerIsBetter) {
    await page.getByLabel("Preference direction").selectOption("decreasing");
  }
  await expect(page.getByLabel("Lower bound", { exact: true })).toHaveValue(String(o.lower));
  await expect(page.getByLabel("Upper bound", { exact: true })).toHaveValue(String(o.upper));
}

export async function waitIdle(page: Page): Promise<void> {
  // every edit goes through the server; "Saving…" never shows for edits, so settle on the network
  await page.waitForLoadState("networkidle");
}

export interface RankedRow {
  rank: number;
  name: string;
  value: string;
}

export async function readRanking(page: Page): Promise<RankedRow[]> {
  const rows = page.getByRole("table", { name: "Ranking" }).locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  const n = await rows.count();
  const out: RankedRow[] = [];
  for (let i = 0; i < n; i++) {
    const cells = rows.nth(i).locator("td, th");
    out.push({
      rank: Number(await cells.nth(0).innerText()),
      name: (await cells.nth(1).innerText()).trim(),
      value: (await cells.nth(2).innerText()).trim(),
    });
  }
  return out;
}

async function enterNumber(page: Page, label: string, value: number): Promise<void> {
  const field = page.getByLabel(label, { exact: true });
  await field.fill(String(value));
  await field.press("Enter");
  await expect(field).toHaveValue(String(value));
}

/** A two-option model built from blank in the GUI: V(Alpha) = 0.6 + 0.2 t and V(Beta) = 0.9 - 0.5 t
 * in the local weight t of Cost, which is 2/3 at the baseline. Returns the new project's ID. */
export async function buildTwoOptionModel(page: Page, title: string): Promise<string> {
  await page.goto("/");
  await page.getByRole("button", { name: "New project…" }).click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  const id = /#\/p\/(.+)$/.exec(page.url())?.[1] ?? "";
  expect(id).not.toBe("");
  await openTab(page, "Alternatives");
  for (const name of ["Alpha", "Beta"]) {
    await page.getByLabel("New alternative name").fill(name);
    await page.getByRole("button", { name: "Add alternative" }).click();
    await expect(page.getByLabel(`Name of alternative ${name}`)).toBeVisible();
  }
  await addTopLevel(page, "Cost");
  await setNumeric(page, { type: "Ratio", unit: "NZD", lower: 0, upper: 100, lowerIsBetter: true });
  await addTopLevel(page, "Quality");
  await setNumeric(page, { type: "Interval", unit: "points", lower: 0, upper: 10 });
  await waitIdle(page);
  await openTab(page, "Measurements");
  for (const [label, value] of [["Alpha on Cost", 20], ["Alpha on Quality", 6], ["Beta on Cost", 60], ["Beta on Quality", 9]] as const) {
    await enterNumber(page, label, value);
  }
  await openTab(page, "Weights");
  await enterNumber(page, "Swing rating for Cost", 100);
  await enterNumber(page, "Swing rating for Quality", 50);
  await waitIdle(page);
  await expect(page.getByLabel("0 errors")).toBeVisible();
  return id;
}
