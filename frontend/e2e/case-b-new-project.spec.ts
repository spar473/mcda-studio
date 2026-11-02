// Case B: a completely unrelated decision (where to live), built from nothing in the application,
// saved, closed, and reopened. Nothing here touches Python or a JSON file by hand.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  addChild,
  addTopLevel,
  cliEvaluate,
  openTab,
  readRanking,
  saveState,
  selectNode,
  setNumeric,
  STORE,
  storedFile,
  waitIdle,
} from "./helpers";
import type { AnalysisExportDocument, Project } from "../src/api/types";
import { globalWeights, overallValue, type Group } from "./oracle";

const TITLE = "Where to live in Auckland";

// The model, in the oracle's terms (the UI is driven from the same table, so a typo cannot hide).
const model: Group = {
  name: "root",
  ratings: { Cost: 100, Lifestyle: 60 },
  children: [
    {
      name: "Cost",
      ratings: { Rent: 100, Commute: 50 },
      children: [
        { name: "Rent", preference: { kind: "linear", lower: 300, upper: 900, direction: "decreasing" } },
        { name: "Commute", preference: { kind: "linear", lower: 0, upper: 60, direction: "decreasing" } },
      ],
    },
    {
      name: "Lifestyle",
      ratings: { Environment: 100, Nightlife: 40 },
      children: [
        {
          name: "Environment",
          ratings: { Climate: 100, "Green space": 25 },
          children: [
            { name: "Climate", preference: { kind: "linear", lower: 4, upper: 14, direction: "increasing" } },
            { name: "Green space", preference: { kind: "labels", mapping: { Low: 0, Medium: 0.5, High: 1 } } },
          ],
        },
        { name: "Nightlife", preference: { kind: "labels", mapping: { Low: 0, Medium: 0.5, High: 1 } } },
      ],
    },
  ],
};

const measurements: Record<string, Record<string, number | string>> = {
  Riverside: { Rent: 520, Commute: 25, Climate: 9, "Green space": "High", Nightlife: "Medium" },
  Hilltop: { Rent: 380, Commute: 50, Climate: 6, "Green space": "Medium", Nightlife: "Low" },
  Downtown: { Rent: 760, Commute: 10, Climate: 11, "Green space": "Low", Nightlife: "High" },
};

const expectedTree = [
  ["Cost", 1],
  ["Rent", 2],
  ["Commute", 2],
  ["Lifestyle", 1],
  ["Environment", 2],
  ["Climate", 3],
  ["Green space", 3],
  ["Nightlife", 2],
] as const;

const oracle = Object.entries(measurements)
  .map(([name, m]) => ({ name, value: overallValue(model, m) }))
  .sort((a, b) => b.value - a.value);

async function readTree(page: Page): Promise<[string, number][]> {
  return page.locator('[role="treeitem"]').evaluateAll((els) =>
    els.map((el): [string, number] => [
      el.querySelector(".tree-name")?.textContent ?? "",
      Number(el.getAttribute("aria-level")),
    ]),
  );
}

async function readGlobalWeights(page: Page): Promise<Record<string, number>> {
  const rows = await page
    .locator('table[aria-label^="Swing ratings under"] tbody tr')
    .evaluateAll((trs) =>
      trs.map((tr): [string, string] => [
        tr.querySelector("th")?.textContent ?? "",
        tr.querySelectorAll("td")[2]?.textContent ?? "",
      ]),
    );
  return Object.fromEntries(rows.filter(([, g]) => g !== "").map(([n, g]) => [n, Number(g)]));
}

async function expectResultsMatchOracle(page: Page): Promise<void> {
  await openTab(page, "Results");
  await expect
    .poll(async () => (await readRanking(page)).map((r) => r.name))
    .toEqual(oracle.map((o) => o.name));
  const ranking = await readRanking(page);
  ranking.forEach((r, i) => {
    expect(r.rank).toBe(i + 1);
    expect(Math.abs(Number(r.value) - (oracle[i]?.value ?? NaN))).toBeLessThan(5.1e-5); // 4 d.p. shown
  });
}

function expectWeightsMatchOracle(shown: Record<string, number>): void {
  const want = globalWeights(model);
  expect(Object.keys(shown).sort()).toEqual(Object.keys(want).sort());
  for (const [name, w] of Object.entries(want)) expect(Math.abs((shown[name] ?? NaN) - w)).toBeLessThan(5.1e-5);
}

async function numberInput(page: Page, label: string, value: number): Promise<void> {
  const field = page.getByLabel(label, { exact: true });
  await field.fill(String(value));
  await field.press("Enter");
  await expect(field).toHaveValue(String(value));
}

let projectId = "";

test.describe.serial("Case B - a new, unrelated project", () => {
  test("build it in the application and save it", async ({ page, request }) => {
    // --- create ---
    await page.goto("/");
    await page.getByRole("button", { name: "New project…" }).click();
    await page.getByLabel("Title", { exact: true }).fill(TITLE);
    await page.getByLabel("Decision maker").fill("Alex");
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: TITLE })).toBeVisible();
    projectId = /#\/p\/(.+)$/.exec(page.url())?.[1] ?? "";
    expect(projectId).not.toBe("");
    await expect(saveState(page)).toHaveText("All changes saved");

    // --- alternatives ---
    await openTab(page, "Alternatives");
    for (const name of Object.keys(measurements)) {
      await page.getByLabel("New alternative name").fill(name);
      await page.getByRole("button", { name: "Add alternative" }).click();
      await expect(page.getByLabel(`Name of alternative ${name}`)).toBeVisible();
    }
    await expect(saveState(page)).toHaveText("● Unsaved changes");

    // --- a three-level tree with three kinds of scale ---
    await addTopLevel(page, "Cost");
    await addChild(page, "Cost", "Rent");
    await setNumeric(page, { type: "Ratio", unit: "NZD/week", lower: 300, upper: 900, lowerIsBetter: true });
    await addChild(page, "Cost", "Commute");
    await setNumeric(page, { type: "Ratio", unit: "minutes", lower: 0, upper: 60, lowerIsBetter: true });
    await addTopLevel(page, "Lifestyle");
    await addChild(page, "Lifestyle", "Environment");
    await addChild(page, "Environment", "Climate");
    await setNumeric(page, { type: "Interval", unit: "°C", lower: 4, upper: 14 });
    await addChild(page, "Environment", "Green space");
    await page.getByLabel("Measurement type").selectOption({ label: "Ordinal (ordered labels)" });
    await addChild(page, "Lifestyle", "Nightlife");
    await page.getByLabel("Measurement type").selectOption({ label: "Ordinal (ordered labels)" });
    await waitIdle(page);
    await openTab(page, "Model");
    expect(await readTree(page)).toEqual(expectedTree.map(([n, l]) => [n, l]));

    // --- measurements ---
    await openTab(page, "Measurements");
    for (const [alt, row] of Object.entries(measurements)) {
      for (const [crit, v] of Object.entries(row)) {
        const control = page.getByLabel(`${alt} on ${crit}`, { exact: true });
        if (typeof v === "number") {
          await control.fill(String(v));
          await control.press("Enter");
          await expect(control).toHaveValue(String(v));
        } else {
          await control.selectOption(v);
        }
      }
    }
    await waitIdle(page);

    // --- swing ratings (a group with one child needs none) ---
    await openTab(page, "Weights");
    const ratings: [string, number][] = [];
    const walk = (g: Group): void => {
      for (const c of g.children) {
        if (g.children.length > 1) ratings.push([c.name, g.ratings[c.name] ?? NaN]);
        if ("children" in c) walk(c);
      }
    };
    walk(model);
    for (const [name, rating] of ratings) await numberInput(page, `Swing rating for ${name}`, rating);
    await waitIdle(page);
    await expect(page.getByLabel("0 errors")).toBeVisible();

    // --- before saving: the application agrees with an independent calculation ---
    await expect.poll(async () => Object.keys(await readGlobalWeights(page)).length).toBe(5);
    expectWeightsMatchOracle(await readGlobalWeights(page));
    await expectResultsMatchOracle(page);
    // nothing has reached the disk yet
    const before = JSON.parse((await storedFile(request, projectId)).toString()) as { alternatives: unknown[] };
    expect(before.alternatives).toHaveLength(0);

    // --- save ---
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    const file = resolve(STORE, `${projectId}.json`);
    const saved = JSON.parse(readFileSync(file, "utf8")) as {
      title: string;
      alternatives: unknown[];
      criteria: unknown[];
      performances: unknown[];
    };
    expect(saved.title).toBe(TITLE);
    expect(saved.alternatives).toHaveLength(3);
    expect(saved.criteria).toHaveLength(8);
    expect(saved.performances).toHaveLength(15);

    // --- the engine, in a separate process on the saved file, agrees as well ---
    const cli = cliEvaluate(file) as { ranking: { name: string; value: number }[] };
    expect(cli.ranking.map((r) => r.name)).toEqual(oracle.map((o) => o.name));
    cli.ranking.forEach((r, i) => expect(Math.abs(r.value - (oracle[i]?.value ?? NaN))).toBeLessThan(1e-12));
  });

  test("close, reload and reopen: nothing has changed", async ({ browser, request }) => {
    const file = resolve(STORE, `${projectId}.json`);
    const bytesBefore = readFileSync(file);

    // a brand-new browser context is "the application, closed and started again"
    const context = await browser.newContext({ baseURL: test.info().project.use.baseURL ?? "" });
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    await expect(page.getByText(TITLE)).toBeVisible();
    await page.getByRole("button", { name: `Open ${TITLE}` }).click();
    await expect(page.getByRole("heading", { level: 1, name: TITLE })).toBeVisible();
    await expect(saveState(page)).toHaveText("All changes saved");

    await openTab(page, "Model");
    expect(await readTree(page)).toEqual(expectedTree.map(([n, l]) => [n, l]));

    await openTab(page, "Alternatives");
    await expect(page.getByRole("table", { name: "Alternatives" }).locator("tbody tr")).toHaveCount(3);

    await openTab(page, "Measurements");
    for (const [alt, row] of Object.entries(measurements)) {
      for (const [crit, v] of Object.entries(row)) {
        const control = page.getByLabel(`${alt} on ${crit}`, { exact: true });
        await expect(control).toHaveValue(String(v));
      }
    }

    await openTab(page, "Weights");
    await expect.poll(async () => Object.keys(await readGlobalWeights(page)).length).toBe(5);
    expectWeightsMatchOracle(await readGlobalWeights(page));
    await expectResultsMatchOracle(page);

    // opening it changed nothing on disk, and the server returns the same bytes
    expect(readFileSync(file).equals(bytesBefore)).toBe(true);
    expect((await storedFile(request, projectId)).equals(bytesBefore)).toBe(true);
    await context.close();
  });
  test("B7 complete graphical workflow: piecewise, profiles, sensitivity, scenarios, exports and fresh reopen", async ({ page, browser, request }, info) => {
    test.setTimeout(90_000);
    await page.goto(`/#/p/${projectId}`);
    await selectNode(page, "Rent");
    await page.getByRole("button", { name: "Open graphical value-function editor" }).click();
    const d = page.getByRole("dialog");
    await expect(d.getByText("Function ready", { exact: true })).toBeVisible();
    await d.getByLabel("Candidate representation").selectOption("piecewise_linear");
    await d.getByLabel("New point measurement").fill("600");
    await d.getByLabel("New point preference").fill(".7");
    await d.getByRole("button", { name: "Add control point", exact: true }).click();
    await expect(d.getByText("Function ready", { exact: true })).toBeVisible();
    await d.getByLabel("Acknowledge candidate range change").check();
    await d.getByRole("button", { name: "Apply candidate" }).click();
    await expect(d).toHaveCount(0);
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    await page.getByRole("button", { name: "Redo", exact: true }).click();
    await openTab(page, "Weights");
    await page.getByRole("button", { name: "Create profile", exact: true }).click();
    await page.getByLabel("Profile name").fill("B7 independent preferences");
    await page.getByRole("button", { name: "Confirm profile change" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByLabel("Swing rating for Cost")).toHaveValue("");
    const profileId = await page.getByLabel("Profile to edit").inputValue();
    expect(profileId).not.toBe("");
    const newRatings: [string, number][] = [["Cost", 80], ["Lifestyle", 100], ["Rent", 100], ["Commute", 50], ["Environment", 100], ["Nightlife", 40], ["Climate", 100], ["Green space", 25]];
    for (const [name, rating] of newRatings) await numberInput(page, `Swing rating for ${name}`, rating);
    await expect(page.getByLabel("0 errors")).toBeVisible();
    await page.getByLabel("Profile to edit").selectOption("");
    await expect(page.getByLabel("Swing rating for Cost")).toHaveValue("100");
    await page.getByLabel("Profile to edit").selectOption(profileId);
    await expect(page.getByLabel("Swing rating for Cost")).toHaveValue("80");
    await openTab(page, "Sensitivity");
    await page.getByLabel("Criterion to vary").selectOption({ label: "Cost (objective)" });
    await expect(page.getByRole("table", { name: "Sensitivity values", exact: true })).toBeVisible();
    const crossover = page.getByLabel("Exact crossovers").getByRole("button").first();
    await expect(crossover).toBeVisible(); await crossover.click();
    await expect(page.getByText("TIED_ALTERNATIVES", { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath("b7-created-model-sensitivity.png") });
    await openTab(page, "Scenarios");
    await page.getByRole("button", { name: "Create scenario", exact: true }).click();
    await page.getByLabel("Scenario name").fill("B7 linear rent and new preferences");
    await page.getByRole("button", { name: "Confirm scenario change" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const scenarioId = await page.getByLabel("Scenario to manage").inputValue();
    await page.getByLabel("Scenario profile", { exact: true }).selectOption(profileId);
    await page.getByRole("button", { name: "Edit override for Rent", exact: true }).click();
    await expect(d.getByText("Function ready", { exact: true })).toBeVisible();
    await d.getByLabel("Candidate representation").selectOption("linear");
    await d.getByLabel("Candidate direction").selectOption("decreasing");
    await d.getByLabel("Acknowledge candidate range change").check();
    await expect(d.getByText("Function ready", { exact: true })).toBeVisible();
    await d.getByRole("button", { name: "Apply candidate" }).click();
    await expect(d).toHaveCount(0);
    await page.getByLabel("Weight profile", { exact: true }).selectOption("");
    await expect(page.getByRole("table", { name: "Scenario comparison", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    const savedBytes = await storedFile(request, projectId);
    const saved = JSON.parse(savedBytes.toString()) as Project;
    expect(saved.criteria.find(c => c.name === "Rent")?.value_function).toMatchObject({ kind: "piecewise_linear", points: [{ x: 300, value: 1 }, { x: 600, value: .7 }, { x: 900, value: 0 }] });
    const costId = saved.criteria.find(c => c.name === "Cost")?.id;
    const lifestyleId = saved.criteria.find(c => c.name === "Lifestyle")?.id;
    if (!costId || !lifestyleId) throw Error("Missing stable criterion IDs");
    expect(saved.weight_profiles[0]?.judgements).toMatchObject({ [costId]: 100, [lifestyleId]: 60 });
    expect(saved.weight_profiles.find(p => p.id === profileId)?.judgements).toMatchObject({ [costId]: 80, [lifestyleId]: 100 });
    await openTab(page, "Results");
    await expect(page.getByRole("table", { name: "Ranking", exact: true })).toBeVisible();
    await expect(page.getByRole("table", { name: "Dominance matrix", exact: true })).toBeVisible();
    const event = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download analysis JSON", exact: true }).click();
    const jsonFile = info.outputPath("b7-built-project-analysis.json"); await (await event).saveAs(jsonFile);
    const document = JSON.parse(readFileSync(jsonFile, "utf8")) as AnalysisExportDocument;
    expect(document.source_project).toEqual(saved);
    expect(document.record.result).toEqual(cliEvaluate(resolve(STORE, `${projectId}.json`), scenarioId));
    const scenarioModel = structuredClone(model); scenarioModel.ratings = { Cost: 80, Lifestyle: 100 };
    for (const alt of document.record.result.ranking) expect(alt.value).toBeCloseTo(overallValue(scenarioModel, measurements[alt.name] ?? {}), 12);
    await page.getByLabel("CSV table", { exact: true }).selectOption("comparison");
    const csvEvent = page.waitForEvent("download"); await page.getByRole("button", { name: "Download CSV", exact: true }).click();
    await (await csvEvent).saveAs(info.outputPath("b7-built-comparison.csv"));
    const svgEvent = page.waitForEvent("download"); await page.getByRole("button", { name: "Download contributions SVG", exact: true }).click();
    await (await svgEvent).saveAs(info.outputPath("b7-built-contributions.svg"));
    await page.getByRole("button", { name: "Contributions", exact: true }).click();
    await page.screenshot({ path: info.outputPath("b7-created-model-results.png") });
    expect((await storedFile(request, projectId)).equals(savedBytes)).toBe(true);
    const fresh = await browser.newContext({ baseURL: test.info().project.use.baseURL ?? "" });
    const reopened = await fresh.newPage(); await reopened.goto("/");
    await reopened.getByRole("button", { name: `Open ${TITLE}`, exact: true }).click();
    await openTab(reopened, "Results"); await reopened.getByLabel("Scenario", { exact: true }).selectOption(scenarioId);
    await expect(reopened.getByRole("table", { name: "Ranking", exact: true })).toBeVisible();
    const reopenedEvent = reopened.waitForEvent("download"); await reopened.getByRole("button", { name: "Download analysis JSON", exact: true }).click();
    const reopenedFile = info.outputPath("b7-reopened-analysis.json"); await (await reopenedEvent).saveAs(reopenedFile);
    expect(JSON.parse(readFileSync(reopenedFile, "utf8"))).toEqual(document);
    expect((await storedFile(request, projectId)).equals(savedBytes)).toBe(true); await fresh.close();
  });
});
