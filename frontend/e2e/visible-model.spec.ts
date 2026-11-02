import { expect, test, type Locator, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Project, ProjectDocument, WeightPreview } from "../src/api/types";
import { addChild, addTopLevel, openTab, readJson, REPO, saveState, storedFile, tab, treeItem, VC_FILE } from "./helpers";

const item = (page: Page, id: string) => page.locator(`[role="treeitem"][data-node-id="${id}"]`);

test("D1 build from blank, accepted names, failed deletion, undo/redo, goal, presentation and reopen", async ({ page, request }, info) => {
  const evaluations: string[] = [];
  page.on("request", r => { if (/\/api\/(evaluate|analysis\/record|sensitivity)/.test(r.url())) evaluations.push(r.url()); });
  await page.goto("/"); await page.getByRole("button", { name: "New project…" }).click();
  await page.getByLabel("Title", { exact: true }).fill("D1 laboratory decision");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("button", { name: "Canvas", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("No criteria yet.", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("d1-blank.png") });
  await addTopLevel(page, "Cost"); await addChild(page, "Cost", "Price");
  await treeItem(page, "Cost").click();
  await page.getByRole("button", { name: "Add child", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Price");
  await page.getByLabel("Name", { exact: true }).press("Enter");
  await expect(page.locator(".tree-name", { hasText: /^Price$/ })).toHaveCount(2);
  const ids = await page.getByRole("treeitem").evaluateAll(nodes => nodes.map(n => n.getAttribute("data-node-id") ?? ""));
  expect(new Set(ids).size).toBe(3);
  const second = item(page, ids[2] ?? "missing");
  await second.locator(".tree-label").click();
  await page.getByRole("button", { name: "Edit selected item", exact: true }).click();
  await expect(page.getByLabel("Name", { exact: true })).toBeFocused();
  await page.getByLabel("Name", { exact: true }).fill("Lifetime cost");
  await expect(second.locator(".tree-name")).toHaveText("Price");
  await page.getByLabel("Name", { exact: true }).press("Enter");
  await expect(second.locator(".tree-name")).toHaveText("Lifetime cost");
  await page.getByRole("button", { name: "Undo", exact: true }).click(); await expect(second.locator(".tree-name")).toHaveText("Price");
  await page.getByRole("button", { name: "Redo", exact: true }).click(); await expect(second.locator(".tree-name")).toHaveText("Lifetime cost");
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(second).toHaveAttribute("aria-selected", "true");
  await page.route("**/api/edit", async route => {
    const body = route.request().postDataJSON() as { operations: { op: string }[] };
    if (body.operations.some(op => op.op === "remove_criterion")) await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: { code: "EDIT_REFUSED", message: "Deletion refused for test", details: [] } }) });
    else await route.continue();
  });
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByText("Deletion refused for test", { exact: true })).toBeVisible();
  await expect(second).toHaveAttribute("aria-selected", "true");
  await page.unroute("**/api/edit");
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(second).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add top-level objective" })).toBeFocused();
  await page.getByRole("button", { name: "Undo", exact: true }).click(); await expect(second).toBeVisible();
  await page.getByRole("button", { name: "Redo", exact: true }).click(); await expect(second).toHaveCount(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await addTopLevel(page, "Temporary");
  const temporary = page.getByRole("treeitem", { name: /Temporary \(/ });
  await temporary.focus(); await temporary.press("ControlOrMeta+z");
  await page.getByRole("treeitem", { name: /New criterion \(/ }).press("ControlOrMeta+z");
  await expect(page.getByRole("button", { name: "Add top-level objective" })).toBeFocused();
  await page.getByRole("button", { name: "Redo", exact: true }).click(); await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(temporary).toBeVisible();
  await page.getByRole("button", { name: "Edit goal: D1 laboratory decision", exact: true }).click();
  await expect(page.getByLabel("Project title", { exact: true })).toBeFocused();
  await page.getByLabel("Project title", { exact: true }).fill("Choose a laboratory site");
  await page.getByLabel("Project title", { exact: true }).press("Enter");
  await expect(page.getByRole("button", { name: "Edit goal: Choose a laboratory site", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click(); await expect(saveState(page)).toHaveText("All changes saved");
  const id = /#\/p\/(.+)$/.exec(page.url())?.[1] ?? "";
  const before = await storedFile(request, id);
  await second.locator(".tree-label").click(); await page.getByRole("button", { name: "Collapse Cost", exact: true }).click();
  const cost = item(page, ids[0] ?? "missing"); await expect(cost).toHaveAttribute("aria-selected", "true"); await expect(cost).toBeFocused();
  await page.getByRole("button", { name: "Outline", exact: true }).click();
  await expect(cost).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await page.getByRole("button", { name: "Expand Cost", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved"); expect((await storedFile(request, id)).equals(before)).toBe(true);
  await page.locator(".model-card").evaluateAll(async nodes => { await Promise.all(nodes.flatMap(n => n.getAnimations().map(a => a.finished))); });
  await page.screenshot({ path: info.outputPath("d1-small.png") });
  await page.reload(); await expect(second).toBeVisible(); await expect(temporary).toBeVisible();
  expect((await storedFile(request, id)).equals(before)).toBe(true); expect(evaluations).toEqual([]);
});

test("D1 keyboard, external reveal and preview request isolation survive presentation changes", async ({ page, request }) => {
  const project = readJson(VC_FILE) as Project; project.id = "d1-request-isolation";
  await request.post("/api/projects/import", { data: project });
  const before = await storedFile(request, project.id); let previews = 0;
  const forbidden: string[] = [];
  // Keyboard moves select as they focus, so a leaf passed over for longer than the preview debounce
  // may legitimately request its own preview. Count only the criterion under test.
  const marketSize = project.criteria.find(c => c.name === "Market Size")?.id;
  expect(marketSize).toBeTruthy();
  page.on("request", r => {
    if (r.url().endsWith("/api/value-functions/preview") &&
        (r.postDataJSON() as { criterion_id?: string } | null)?.criterion_id === marketSize) previews++;
    if (/\/api\/(edit|evaluate|analysis\/record|sensitivity)/.test(r.url()) || r.method() === "PUT") forbidden.push(r.url());
  });
  await page.goto(`/#/p/${project.id}`);
  const first = page.getByRole("treeitem").first(); await first.focus(); await first.press("ArrowRight");
  await expect(page.getByRole("treeitem", { name: /Founder/ })).toBeFocused();
  await page.getByRole("treeitem").filter({ has: page.locator(".tree-name", { hasText: /^Founder/ }) }).press("Home");
  await expect(first).toBeFocused();
  await treeItem(page, "Market Size").click();
  await expect.poll(() => previews).toBe(1);
  await expect(page.getByRole("region", { name: "Value-function preview" })).toContainText("Function ready");
  await page.getByRole("button", { name: "Outline", exact: true }).click();
  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await page.getByRole("button", { name: "Collapse Team", exact: true }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Market Size");
  await page.getByRole("button", { name: "Expand Team", exact: true }).click();
  expect(previews).toBe(1); expect(forbidden).toEqual([]);
  await treeItem(page, "Market").focus(); await page.getByRole("treeitem", { name: /^Market \(/ }).press("Enter");
  await expect(page.getByLabel("Name", { exact: true })).toBeFocused();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true);
});

test("D1 malformed incoming structure is explicit and complete, without looping", async ({ page, request }) => {
  const doc = await (await request.post("/api/projects", { data: { title: "Malformed incoming fixture" } })).json() as ProjectDocument;
  doc.project.criteria = [
    { id: "a", name: "Cycle A", parent_id: "b", order: 0, description: "", scale: null, value_function: null },
    { id: "b", name: "Cycle B", parent_id: "a", order: 0, description: "", scale: null, value_function: null },
  ];
  doc.validation.issues.push({ severity: "error", code: "INVALID_TREE", path: "criteria", message: "Correct the cyclic hierarchy" });
  await page.route(`**/api/projects/${doc.project.id}`, route => route.fulfill({ json: doc }));
  await page.goto(`/#/p/${doc.project.id}`);
  await expect(page.getByRole("region", { name: "Structure cannot be drawn safely" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Incoming criteria (flat fallback)" }).getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("complementary", { name: "Problems" })).toContainText("Correct the cyclic hierarchy");
  await expect(page.getByRole("button", { name: "Add top-level objective" })).toBeDisabled();
});

test("D1 clicking the goal straight after typing a rename still moves focus into the project title", async ({ page }) => {
  await page.goto("/"); await page.getByRole("button", { name: "New project…" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Focus after rename");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await addTopLevel(page, "Cost");
  // Hold the edit response: the rename started by the blur is still pending while the goal is clicked.
  let release: () => void = () => undefined;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/edit", async route => { await held; await route.continue(); });
  await page.getByLabel("Name", { exact: true }).fill("Total cost"); // neither Enter nor an explicit blur
  await page.getByRole("button", { name: "Edit goal: Focus after rename", exact: true }).click();
  const title = page.getByLabel("Project title", { exact: true });
  await expect(title).toBeDisabled();
  release();
  await expect(title).toBeEnabled();
  await expect(title).toBeFocused();
  await expect(page.locator(".tree-name", { hasText: /^Total cost$/ })).toBeVisible();
});

test("Canvas diagram: value-tree layout, engine weights, editor shortcuts and a read-only presentation", async ({ page, request }) => {
  const project = readJson(VC_FILE) as Project; project.id = "canvas-diagram";
  await request.post("/api/projects/import", { data: project });
  const before = await storedFile(request, project.id);
  const engine = await (await request.post("/api/weights/preview", { data: { project } })).json() as WeightPreview;
  let weightRequests = 0;
  const forbidden: string[] = [];
  page.on("request", r => {
    if (r.url().endsWith("/api/weights/preview")) weightRequests++;
    if (/\/api\/(edit|evaluate|analysis\/record|sensitivity)/.test(r.url()) || r.method() === "PUT") forbidden.push(r.url());
  });
  await page.goto(`/#/p/${project.id}`);
  const diagram = page.getByRole("region", { name: "Model diagram", exact: true });
  const card = (id: string) => item(page, id).locator(".model-card");
  const options = diagram.getByRole("region", { name: "Alternatives in the model diagram" });
  await expect(options.getByRole("button")).toHaveText(["Hyades", "Forever Harvest", "Kura Dynamics", "Outlier Space"]);
  await expect(options).toContainText("scored on all 8 leaf criteria");
  // Goal → objective → criterion → options, left to right, like the original study's value-tree figure.
  const x = async (l: Locator) => (await l.boundingBox())?.x ?? NaN;
  const goalX = await x(diagram.getByRole("button", { name: /^Edit goal:/ }));
  expect(goalX).toBeLessThan(await x(card("team")));
  expect(await x(card("team"))).toBeLessThan(await x(card("founder_expertise")));
  expect(await x(card("founder_expertise"))).toBeLessThan(await x(options));
  // Weights are the engine's, rounded only for display; selection and collapse never re-request them.
  const global = engine.global_weights["founder_expertise"]?.toFixed(3) ?? "missing";
  await expect(item(page, "founder_expertise")).toHaveAccessibleName(new RegExp(`global weight ${global}$`));
  await expect(card("team")).toContainText(`of goal ${engine.path_shares["team"]?.toFixed(3) ?? "missing"}`);
  const settled = weightRequests;
  expect(settled).toBeGreaterThan(0);
  await item(page, "market_size").locator(".tree-label").click();
  await page.getByRole("button", { name: "Collapse Market", exact: true }).click();
  await page.getByRole("button", { name: "Expand Market", exact: true }).click();
  await page.waitForTimeout(400);
  expect(weightRequests).toBe(settled); expect(forbidden).toEqual([]);
  // Chips open the existing destinations; the Inspector offers the same route by keyboard.
  await page.getByRole("button", { name: "Edit swing weights under Team", exact: true }).click();
  await expect(tab(page, "Weights")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Swing rating for Founder Expertise", { exact: true })).toBeFocused();
  await openTab(page, "Model");
  await page.getByRole("button", { name: "Edit value function for Founder Expertise", exact: true }).click();
  await expect(page.getByRole("dialog", { name: /Edit value function · Founder Expertise/ })).toBeVisible();
  await page.getByRole("button", { name: "Cancel candidate", exact: true }).click();
  await page.getByRole("button", { name: "Edit alternative: Kura Dynamics", exact: true }).click();
  await expect(page.getByLabel("Name of alternative Kura Dynamics", { exact: true })).toBeFocused();
  await openTab(page, "Model");
  await item(page, "traction").focus(); await item(page, "traction").press("Space");
  await page.getByRole("button", { name: "Edit swing weights for this group", exact: true }).click();
  await expect(page.getByLabel("Swing rating for Customer Validation", { exact: true })).toBeFocused();
  // Presentation: read-only, explicit about the live draft, and leaves the stored project untouched.
  await openTab(page, "Model");
  await page.getByRole("button", { name: "Present", exact: true }).click();
  await expect(page.getByRole("heading", { level: 2, name: project.title })).toBeFocused();
  await expect(page.getByTestId("presentation-context")).toContainText("saved revision");
  await expect(page.getByRole("button", { name: /^Edit (value function|swing|alternative|goal)/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add top-level objective" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Present", exact: true })).toBeFocused();
  expect((await storedFile(request, project.id)).equals(before)).toBe(true); expect(forbidden).toEqual([]);
});

function maximumProject(shape: "broad" | "deep", id: string): Project {
  const p = readJson(resolve(REPO, "tests/fixtures/performance_project.json")) as Project;
  const criteria: Project["criteria"] = [];
  const branch = (key: string, parent: string | null) => criteria.push({ id: key, parent_id: parent, name: `Objective ${key}`, order: criteria.length, description: "", scale: null, value_function: null });
  const leaf = (i: number, parent: string) => criteria.push({ id: `leaf_${String(i)}`, parent_id: parent,
    name: `Criterion ${String(i)} — a readable long label explaining the actual measured outcome without truncating important words`, order: i, description: "",
    scale: { type: "interval", anchor_mode: "fixed", lower: 0, upper: 10, unit: "units", labels: [] }, value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } });
  if (shape === "deep") {
    for (let i = 0; i < 900; i++) branch(`n${String(i)}`, i ? `n${String(i - 1)}` : null);
    for (let i = 0; i < 100; i++) leaf(i, "n899");
  } else {
    branch("root", null);
    for (let i = 0; i < 100; i++) {
      let parent = "root";
      for (let j = 0; j < (i === 99 ? 8 : 9); j++) { const key = `b${String(i)}_${String(j)}`; branch(key, parent); parent = key; }
      leaf(i, parent);
    }
  }
  p.id = id; p.title = `D1 ${shape} fixture`; p.criteria = criteria; p.scenarios = [];
  p.alternatives = Array.from({ length: 100 }, (_, i) => ({ id: `a${String(i)}`, name: `Option ${String(i)}`, metadata: {} }));
  p.performances = p.alternatives.flatMap(a => Array.from({ length: 100 }, (_, i) => ({ alternative_id: a.id, criterion_id: `leaf_${String(i)}`, value: 5 })));
  p.weight_profiles = [{ id: "default", name: "Default", method: "swing", judgements: Object.fromEntries(criteria.map(n => [n.id, 1])) }];
  p.analysis = { method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} }; return p;
}

test("D1 measured fixtures, narrow layout, long names and reduced motion", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const result = await original(...args); const json = result.json.bind(result);
      if (/\/api\/projects\/[^/]+$/.test(result.url)) result.json = async () => { const doc: unknown = await json(); performance.mark("d1-received"); return doc; };
      return result;
    };
  });
  const standard = readJson(resolve(REPO, "tests/fixtures/performance_project.json")) as Project; standard.id = "d1-standard";
  const fixtures = [standard, maximumProject("broad", "d1-broad"), maximumProject("deep", "d1-deep")];
  const metrics: unknown[] = [];
  for (const fixture of fixtures) {
    expect((await request.post("/api/projects/import", { data: fixture })).status()).toBe(201);
    const initial: number[] = [], selection: number[] = [], collapse: number[] = [], expand: number[] = [];
    for (let run = 0; run < 5; run++) {
      if (run === 0) await page.goto(`/#/p/${fixture.id}`); else await page.reload();
      await expect(page.getByRole("treeitem")).toHaveCount(fixture.criteria.length);
      initial.push(await page.evaluate(() => performance.now() - (performance.getEntriesByName("d1-received").at(-1)?.startTime ?? performance.now())));
      const root = page.getByRole("treeitem").first();
      const selected = await root.evaluate(async el => { const start = performance.now(); (el.querySelector(".tree-label") as HTMLButtonElement).click(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); return performance.now() - start; });
      selection.push(selected);
      const collapsed = await root.evaluate(async el => { const start = performance.now(); (el.querySelector(".twisty") as HTMLButtonElement).click(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); return performance.now() - start; });
      collapse.push(collapsed);
      expand.push(await root.evaluate(async el => { const start = performance.now(); (el.querySelector(".twisty") as HTMLButtonElement).click(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); return performance.now() - start; }));
    }
    metrics.push({ id: fixture.id, nodes: fixture.criteria.length, alternatives: fixture.alternatives.length, measurements: fixture.performances.length, initial_ms: initial, selection_ms: selection, collapse_ms: collapse, expand_ms: expand });
    await page.screenshot({ path: info.outputPath(`${fixture.id}.png`) });
    if (fixture.id === "d1-deep") {
      await page.setViewportSize({ width: 600, height: 900 });
      const last = page.getByRole("treeitem").last(); await last.scrollIntoViewIfNeeded(); await last.locator(".tree-label").click();
      await expect(last.locator(".tree-name")).toContainText("without truncating");
      await expect(page.getByLabel("Name", { exact: true })).toHaveValue(fixture.criteria.at(-1)?.name ?? "");
      await page.screenshot({ path: info.outputPath("d1-deep-long-narrow.png") });
      expect(await last.locator(".model-card").evaluate(el => getComputedStyle(el).animationName)).toBe("none");
      await page.setViewportSize({ width: 1360, height: 860 });
      await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
      await page.getByRole("button", { name: "Edit goal:", exact: false }).click();
      await expect(page.getByLabel("Project title", { exact: true })).toBeFocused();
      // The diagram keeps fixed card columns and scrolls inside a usable region instead of squeezing them.
      const goal = await page.getByRole("button", { name: "Edit goal:", exact: false }).boundingBox();
      const region = await page.getByRole("region", { name: "Model diagram", exact: true }).boundingBox();
      expect(goal?.width ?? 0).toBeGreaterThan(280);
      expect(region?.width ?? 0).toBeGreaterThan(400);
      await page.screenshot({ path: info.outputPath("d1-zoom.png") });
    }
  }
  writeFileSync(info.outputPath("d1-performance.json"), JSON.stringify({ environment: { browser: page.context().browser()?.version(), platform: process.platform, node: process.version }, metrics, note: "Initial is from project JSON receipt to observed DOM; selection/collapse/expand include two requestAnimationFrame callbacks; five runs each, reduced motion." }, null, 2));
});
