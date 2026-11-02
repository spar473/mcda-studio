import { expect, test, type Locator, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Project, ProjectDocument } from "../src/api/types";
import { openTab, readJson, REPO, saveState, storedFile } from "./helpers";

const supplier = () => readJson(resolve(REPO, "examples/supplier_selection/project.json")) as Project;
const matrix = (page: Page) => page.getByRole("table", { name: "Measurement coverage: alternatives by leaf criteria", exact: true });
const cell = (page: Page, a: string, c: string) => matrix(page).getByRole("button", { name: new RegExp(`\\(${a}\\) on .*\\(${c}\\):`) });
const summary = (page: Page) => page.getByTestId("coverage-summary");
const back = (page: Page) => page.getByRole("button", { name: "Return to coverage", exact: true });

function watchWrites(page: Page) {
  const calls: string[] = [];
  page.on("request", r => {
    if (/\/api\/(edit|evaluate|analysis\/record|sensitivity)/.test(r.url()) || r.method() === "PUT") calls.push(r.url());
  });
  return calls;
}

test("measurement coverage finds a missing cell, enters zero and follows undo and redo", async ({ page, request }) => {
  const p = supplier(); p.id = "coverage-missing-zero";
  p.performances = p.performances.filter(v => v.alternative_id !== "apex" || v.criterion_id !== "defect_rate");
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id), calls = watchWrites(page);
  await page.goto(`/#/p/${p.id}`);
  await expect(summary(page)).toHaveText("39/40 entered; 1 missing; 0 entered cells need attention");
  await page.getByRole("button", { name: "Collapse Performance", exact: true }).click();
  await expect(summary(page)).toContainText("39/40 entered; 1 missing");
  const missing = cell(page, "apex", "defect_rate"); await expect(missing).toHaveAccessibleName(/: Missing$/);
  await expect(missing).toContainText("no measurement"); await missing.click();
  const input = page.getByLabel("Apex Components on Defect rate", { exact: true });
  await expect(input).toBeFocused(); await expect(input).toHaveValue("");
  await back(page).click(); await expect(cell(page, "apex", "defect_rate")).toBeFocused();
  expect(calls).toEqual([]); expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  await cell(page, "apex", "defect_rate").click(); await input.fill("0"); await input.press("Enter");
  await expect(input).toHaveValue("0"); await back(page).click();
  await expect(cell(page, "apex", "defect_rate")).toBeFocused();
  await expect(summary(page)).toHaveText("40/40 entered; 0 missing; 0 entered cells need attention");
  await expect(cell(page, "apex", "defect_rate")).toContainText("Stored: 0");
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(summary(page)).toContainText("39/40 entered; 1 missing");
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(summary(page)).toContainText("40/40 entered; 0 missing");
  expect(calls.filter(url => url.endsWith("/api/edit"))).toHaveLength(1);
  expect(calls.filter(url => !url.endsWith("/api/edit"))).toEqual([]);
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
});

test("measurement coverage keyboard and issue links preserve stored bytes and history", async ({ page, request }, info) => {
  const p = supplier(); p.id = "coverage-keyboard";
  const bad = p.performances.find(v => v.alternative_id === "apex" && v.criterion_id === "defect_rate");
  if (!bad) throw Error("fixture has no defect rate"); bad.value = -1;
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id), calls = watchWrites(page);
  const doc = await (await request.get(`/api/projects/${p.id}`)).json() as ProjectDocument;
  await page.emulateMedia({ reducedMotion: "reduce" }); await page.goto(`/#/p/${p.id}`);
  await expect(summary(page)).toHaveText("40/40 entered; 0 missing; 1 entered cell needs attention");
  const first = cell(page, "apex", "unit_price"); await first.focus(); await first.press("ArrowRight");
  await expect(cell(page, "apex", "logistics_cost")).toBeFocused();
  await page.keyboard.press("ArrowDown"); await expect(cell(page, "brightline", "logistics_cost")).toBeFocused();
  await page.keyboard.press("Home"); await expect(cell(page, "brightline", "unit_price")).toBeFocused();
  await page.keyboard.press("End"); await expect(cell(page, "brightline", "region")).toBeFocused();
  await page.keyboard.press("Enter"); await expect(page.getByLabel("Brightline Supply on Sourcing region", { exact: true })).toBeFocused();
  await openTab(page, "Model"); await expect(cell(page, "brightline", "region")).toBeFocused();
  await cell(page, "apex", "defect_rate").focus();
  await expect(cell(page, "apex", "defect_rate")).toContainText("Entered · needs attention");
  const detail = page.getByRole("region", { name: "Selected coverage cell" });
  await detail.getByRole("button", { name: /^NEGATIVE_RATIO_VALUE:/ }).click();
  await expect(page.getByLabel("Apex Components on Defect rate", { exact: true })).toBeFocused();
  await back(page).click(); await expect(cell(page, "apex", "defect_rate")).toBeFocused();
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  await expect(saveState(page)).toHaveText("All changes saved");
  const after = await (await request.get(`/api/projects/${p.id}`)).json() as ProjectDocument;
  expect(after.fingerprint).toBe(doc.fingerprint); expect((await storedFile(request, p.id)).equals(before)).toBe(true); expect(calls).toEqual([]);
  await page.setViewportSize({ width: 600, height: 900 }); await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await matrix(page).scrollIntoViewIfNeeded();
  await expect(page.getByRole("region", { name: "Measurement coverage table scroll area" })).toBeVisible();
  const pane = await page.getByRole("tabpanel").boundingBox(); expect(pane?.height ?? 0).toBeGreaterThanOrEqual(190);
  const visibleCell = cell(page, "apex", "defect_rate"); await visibleCell.scrollIntoViewIfNeeded(); await expect(visibleCell).toBeInViewport();
  expect(await cell(page, "apex", "defect_rate").evaluate(el => getComputedStyle(el).transitionDuration)).toBe("0s");
  await page.screenshot({ path: info.outputPath("measurement-coverage-narrow.png") });
});

test("measurement coverage sends an unconfigured leaf to setup with focus return", async ({ page, request }) => {
  const p = supplier(); p.id = "coverage-setup";
  const n = p.criteria.find(n => n.id === "defect_rate"); if (!n) throw Error("missing fixture criterion"); n.scale = null; n.value_function = null;
  p.performances = p.performances.filter(v => v.criterion_id !== "defect_rate");
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${p.id}`);
  await expect(cell(page, "cobalt", "defect_rate")).toHaveText("Missing · setup needed");
  await cell(page, "cobalt", "defect_rate").click();
  await expect(page.getByLabel("Measurement type", { exact: true })).toBeFocused();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Defect rate");
  await back(page).click(); await expect(cell(page, "cobalt", "defect_rate")).toBeFocused();
});

function maximumProject(shape: "broad" | "deep"): Project {
  const p = readJson(resolve(REPO, "tests/fixtures/performance_project.json")) as Project;
  const criteria: Project["criteria"] = [];
  const branch = (id: string, parent_id: string | null) => criteria.push({ id, parent_id, name: `Objective ${id}`, order: criteria.length, description: "", scale: null, value_function: null });
  const leaf = (i: number, parent_id: string) => criteria.push({ id: `leaf_${String(i)}`, parent_id, name: `Criterion ${String(i)} with a descriptive measured outcome`, order: i, description: "",
    scale: { type: "interval", lower: 0, upper: 100, anchor_mode: "fixed", unit: "units", labels: [] },
    value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } });
  if (shape === "deep") {
    for (let i = 0; i < 900; i++) branch(`n${String(i)}`, i ? `n${String(i - 1)}` : null);
    for (let i = 0; i < 100; i++) leaf(i, "n899");
  } else {
    branch("root", null);
    for (let i = 0; i < 100; i++) {
      let parent = "root";
      for (let j = 0; j < (i === 99 ? 8 : 9); j++) { const id = `b${String(i)}_${String(j)}`; branch(id, parent); parent = id; }
      leaf(i, parent);
    }
  }
  p.id = `coverage-${shape}`; p.title = `Measurement coverage ${shape} benchmark`; p.criteria = criteria; p.scenarios = [];
  p.alternatives = Array.from({ length: 100 }, (_, i) => ({ id: `a${String(i)}`, name: `Option ${String(i)}`, metadata: {} }));
  p.performances = p.alternatives.flatMap(a => Array.from({ length: 100 }, (_, i) => ({ alternative_id: a.id, criterion_id: `leaf_${String(i)}`, value: 5 })));
  p.weight_profiles = [{ id: "default", name: "Default", method: "swing", judgements: Object.fromEntries(criteria.map(n => [n.id, 1])) }];
  p.analysis = { method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} }; return p;
}

async function paintedClick(target: Locator) {
  return target.evaluate(async el => {
    const start = performance.now(); (el as HTMLButtonElement).focus();
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (!document.activeElement?.matches('.coverage-cell[aria-pressed="true"]')) throw Error("selection did not paint");
    return performance.now() - start;
  });
}

test("measurement coverage pages large models and measures five canvas and interaction paints", async ({ page, request }, info) => {
  test.setTimeout(180_000); await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args), json = response.json.bind(response);
      if (/\/api\/projects\/[^/]+$/.test(response.url) || response.url.endsWith("/api/edit")) response.json = async () => {
        const doc = await json() as { project: { criteria: { id: string; name: string }[] } };
        const initial = !response.url.endsWith("/api/edit"), prefix = initial ? "coverage-initial" : "coverage-edit";
        const start = performance.now();
        const observe = () => {
          const label = document.querySelector("[data-node-id] .tree-name");
          if (!document.querySelector(".coverage-matrix") || label?.textContent !== doc.project.criteria[0]?.name) return false;
          observer.disconnect();
          requestAnimationFrame(() => requestAnimationFrame(() => performance.measure(prefix, { start, end: performance.now() })));
          return true;
        };
        const observer = new MutationObserver(observe); observer.observe(document, { childList: true, subtree: true, characterData: true });
        return doc;
      };
      return response;
    };
  });
  const standard = readJson(resolve(REPO, "tests/fixtures/performance_project.json")) as Project; standard.id = "coverage-standard";
  const metrics: unknown[] = [];
  for (const fixture of [standard, maximumProject("broad"), maximumProject("deep")]) {
    expect((await request.post("/api/projects/import", { data: fixture })).status()).toBe(201);
    const initial: number[] = [], edit: number[] = [], selection: number[] = [], dom: number[] = [], elements: number[] = [];
    for (let run = 0; run < 5; run++) {
      await page.goto(`/#/p/${fixture.id}`); if (run) await page.reload();
      await expect(page.getByRole("treeitem")).toHaveCount(fixture.criteria.length);
      await expect(summary(page)).toContainText(`${String(fixture.performances.length)}/${String(fixture.performances.length)} entered; 0 missing`);
      await expect.poll(() => page.evaluate(() => performance.getEntriesByName("coverage-initial").length)).toBeGreaterThan(0);
      initial.push(await page.evaluate(() => performance.getEntriesByName("coverage-initial").at(-1)?.duration ?? NaN));
      dom.push(await matrix(page).locator(".coverage-cell").count()); expect(dom.at(-1)).toBe(400);
      elements.push(await page.locator(".model-workspace *").count());
      await expect(matrix(page).locator("input, select")).toHaveCount(0);
      expect(await matrix(page).locator("thead th button").evaluateAll(buttons => buttons.every(button => button.scrollWidth <= button.clientWidth))).toBe(true);
      selection.push(await paintedClick(matrix(page).locator(".coverage-cell").first()));
      // Rename the first branch through its existing Inspector while the canvas stays visible.
      await page.getByRole("treeitem").first().locator(".tree-label").click();
      const name = page.getByLabel("Name", { exact: true }); await name.fill(`Measured objective ${String(run)}`); await name.press("Enter");
      await expect.poll(() => page.evaluate(() => performance.getEntriesByName("coverage-edit").length)).toBeGreaterThan(0);
      edit.push(await page.evaluate(() => performance.getEntriesByName("coverage-edit").at(-1)?.duration ?? NaN));
      await expect(page.getByRole("treeitem").first().locator(".tree-name")).toHaveText(`Measured objective ${String(run)}`);
      // Undo resets the saved revision for the next load without writing the project file.
      await page.getByRole("button", { name: "Undo", exact: true }).click(); await expect(saveState(page)).toHaveText("All changes saved");
    }
    metrics.push({ id: fixture.id, nodes: fixture.criteria.length, alternatives: fixture.alternatives.length,
      measurements: fixture.performances.length, initial_ms: initial, accepted_edit_ms: edit, selection_ms: selection, cell_buttons: dom, canvas_dom_elements: elements });
    const navigationBefore = await storedFile(request, fixture.id), navigationCalls = watchWrites(page);
    await page.getByRole("button", { name: "Next alternatives", exact: true }).click();
    await page.getByRole("button", { name: "Next criteria", exact: true }).click();
    const target = matrix(page).locator(".coverage-cell").last(), label = await target.getAttribute("aria-label");
    await target.focus(); await target.press("Enter");
    await expect(page.getByRole("table", { name: "Performance table" }).locator("input, select")).toHaveCount(400);
    await expect(page.locator("input:focus, select:focus")).toHaveCount(1);
    await back(page).click(); await expect(matrix(page).getByRole("button", { name: label ?? "missing", exact: true })).toBeFocused();
    if (fixture.alternatives.length === 100) {
      await page.keyboard.press("End");
      for (let r = 0; r < 3; r++) await page.getByRole("button", { name: "Next alternatives", exact: true }).click();
      await expect(page.getByRole("group", { name: "Measurement pages" })).toContainText("Alternatives 81–100 of 100; criteria 81–100 of 100");
      await expect(cell(page, "a99", "leaf_99")).toBeVisible();
    }
    await page.screenshot({ path: info.outputPath(`${fixture.id}.png`) });
    expect((await storedFile(request, fixture.id)).equals(navigationBefore)).toBe(true);
    expect(navigationCalls).toEqual([]);
    await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  }
  writeFileSync(info.outputPath("measurement-coverage-performance.json"), JSON.stringify({
    environment: { browser: page.context().browser()?.version(), platform: process.platform, node: process.version, viewport: page.viewportSize(), reduced_motion: true }, metrics,
    method: "Five runs per fixture. Initial: parsed project JSON to canvas DOM plus two animation frames. Edit: parsed accepted edit response to renamed canvas label plus two frames. Selection: cell focus and ArrowRight to two frames. Backend/transport excluded from receipt-based timings. No animation delay.",
  }, null, 2));
});
