// Case A: the NZ deep-tech VC reference project is opened in the application, all model inputs are
// preserved byte for byte, and the application reproduces the report's results.
import { expect, test } from "@playwright/test";
import {
  at,
  VC_FILE,
  openTab,
  readJson,
  readRanking,
  saveState,
  storedFile,
} from "./helpers";
import { readFileSync } from "node:fs";

interface ProjectFile {
  id: string;
  title: string;
  alternatives: { id: string; name: string }[];
  criteria: { id: string; name: string; parent_id: string | null }[];
  scenarios: { id: string; name: string }[];
}
const project = readJson(VC_FILE) as ProjectFile;
const nameOf = (id: string): string | undefined => project.alternatives.find((x) => x.id === id)?.name;

test.describe.serial("Case A - NZ deep-tech VC reference project", () => {
  test("add the bundled example and open it", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Examples…" }).click();
    await page.getByRole("button", { name: `Add ${project.title}` }).click();
    await expect(page.getByRole("heading", { level: 1, name: project.title })).toBeVisible();
    await expect(saveState(page)).toHaveText("All changes saved");
  });

  test("the model structure is exactly the stored one", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await expect(saveState(page)).toHaveText("All changes saved");
    const items = page.getByRole("treeitem");
    await expect(items).toHaveCount(project.criteria.length); // 4 objectives + 8 criteria
    for (const c of project.criteria) {
      await expect(page.locator(".tree-name", { hasText: new RegExp(`^${c.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) })).toBeVisible();
    }
    await openTab(page, "Alternatives");
    const rows = page.getByRole("table", { name: "Alternatives" }).locator("tbody tr");
    await expect(rows).toHaveCount(project.alternatives.length);
  });

  test("validation: complete model, only the two documented local-anchor warnings", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await expect(page.getByLabel("0 errors")).toBeVisible();
    await expect(page.getByLabel("2 warnings")).toBeVisible();
    await expect(page.locator(".validation .code", { hasText: "LOCAL_ANCHORS" })).toHaveCount(2);
  });

  test("results reproduce the report: base model", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Results");
    await expect(page.getByRole("table", { name: "Ranking" })).toBeVisible();
    await expect
      .poll(async () => (await readRanking(page)).map((r) => r.name))
      .toEqual(["forever_harvest", "outlier_space", "kura_dynamics", "hyades"].map(nameOf));
    const ranking = await readRanking(page);
    // report prints 0.723 / 0.660 / 0.599 / 0.573; the application shows four decimals
    expect(ranking.map((r) => r.value)).toEqual(["0.7227", "0.6599", "0.5986", "0.5734"]);
    expect(ranking.map((r) => Number(r.value).toFixed(3))).toEqual(["0.723", "0.660", "0.599", "0.573"]);
  });

  test("results reproduce the report: linear Market Size scenario", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Results");
    await page.getByLabel("Scenario").selectOption({ label: at(project.scenarios, 0).name });
    await expect
      .poll(async () => (await readRanking(page)).map((r) => r.value))
      .toEqual(["0.7227", "0.6523", "0.5734", "0.5561"]);
    const names = (await readRanking(page)).map((r) => r.name);
    // Hyades overtakes Kura under the linear Market Size value function
    expect(names).toEqual(["forever_harvest", "outlier_space", "hyades", "kura_dynamics"].map(nameOf));
  });

  test("weights shown equal the report's printed global weights", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Weights");
    const table = page.getByRole("table", { name: /Swing ratings under/ });
    await expect(table.first()).toBeVisible();
    const globals = page.locator("table td.num:nth-child(4)");
    await expect.poll(async () => (await globals.allInnerTexts()).filter(Boolean).length).toBe(8);
    expect((await globals.allInnerTexts()).filter(Boolean).sort()).toEqual(
      ["0.1783", "0.1159", "0.1254", "0.1393", "0.1307", "0.1046", "0.1211", "0.0848"].sort(),
    );
  });

  test("looking at the project changed nothing: the stored file is byte-identical", async ({ page, request }) => {
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Results");
    await openTab(page, "Measurements");
    expect((await storedFile(request, project.id)).equals(readFileSync(VC_FILE))).toBe(true);
  });

  test("an edit marks the project unsaved, undo makes it clean again, and nothing was written", async ({ page, request }) => {
    await page.goto(`/#/p/${project.id}`);
    await openTab(page, "Alternatives");
    const first = at(project.alternatives, 0);
    const name = page.getByLabel(`Name of alternative ${first.name}`);
    await name.fill(`${first.name} (edited)`);
    await name.press("Enter");
    await expect(saveState(page)).toHaveText("● Unsaved changes");
    expect((await storedFile(request, project.id)).equals(readFileSync(VC_FILE))).toBe(true);
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
  });

  test("close and reopen from the dashboard gives the same results", async ({ page }) => {
    await page.goto(`/#/p/${project.id}`);
    await page.getByRole("button", { name: "← Projects" }).click();
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    await page.getByRole("button", { name: `Open ${project.title}` }).click();
    await openTab(page, "Results");
    await expect
      .poll(async () => (await readRanking(page)).map((r) => r.value))
      .toEqual(["0.7227", "0.6599", "0.5986", "0.5734"]);
  });
});
