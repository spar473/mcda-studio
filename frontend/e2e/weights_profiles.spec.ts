import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { MavtResult, Project, WeightPreview } from "../src/api/types";
import { VC_FILE, REPO, at, cliEvaluate, openTab, readJson, readRanking, saveState, storedFile } from "./helpers";

const INFRA_FILE = resolve(REPO, "examples/infrastructure_procurement/project.json");

/** The engine's own numbers for a project and profile, fetched over the API. */
async function enginePreview(page: Page, project: Project, profileId: string | null): Promise<WeightPreview> {
  const r = await page.request.post("/api/weights/preview", { data: { project, configuration: {
    method: "mavt", scenario_id: null, weight_profile_id: profileId, parameters: {},
  } } });
  expect(r.ok()).toBeTruthy();
  return await r.json() as WeightPreview;
}

const rating = (page: Page, name: string) => page.getByLabel(`Swing rating for ${name}`, { exact: true });

async function setRating(page: Page, name: string, value: string): Promise<void> {
  const field = rating(page, name);
  await field.fill(value);
  await field.press("Enter");
  await expect(field).toHaveValue(value);
}

async function profileCommand(page: Page, button: string, fill?: { name?: string; replacement?: string }): Promise<void> {
  await page.getByRole("button", { name: button, exact: true }).click();
  if (fill?.name !== undefined) await page.getByLabel("Profile name").fill(fill.name);
  if (fill?.replacement !== undefined) await page.getByLabel("Replacement profile").selectOption(fill.replacement);
  const confirm = page.getByRole("button", { name: fill?.replacement !== undefined ? "Delete and replace references" : "Confirm profile change" });
  await confirm.click();
  await expect(confirm).toHaveCount(0);
}

/** Every displayed weight equals the engine's, to the digits the GUI prints. */
async function expectWeightsMatchEngine(page: Page, project: Project, preview: WeightPreview): Promise<void> {
  const tree = page.locator(".weight-tree");
  const named = (id: string) => at(project.criteria.filter((c) => c.id === id), 0).name;
  for (const [id, local] of Object.entries(preview.local_weights)) {
    const row = tree.locator("li").filter({ has: page.getByRole("button", { name: named(id), exact: true }) }).first();
    await expect(row).toContainText(`local ${local.toFixed(4)}`);
    // The bar carries the engine's full-precision value, not the rounded label.
    await expect(row.getByRole("meter", { name: `Tree local weight for ${named(id)}` }).first())
      .toHaveJSProperty("value", local);
    // Raw ratings stay visibly distinct from the derived weights beside them.
    const raw = project.weight_profiles.find((x) => x.id === preview.weight_profile_id)?.judgements[id];
    await expect(row).toContainText(raw === undefined ? "raw not supplied" : `raw ${String(raw)}`);
  }
  // Leaves show a global weight; objectives show a branch share, never relabelled as global.
  for (const [id, global] of Object.entries(preview.global_weights)) {
    await expect(tree.locator("li").filter({ has: page.getByRole("button", { name: named(id), exact: true }) }).first())
      .toContainText(`global ${global.toFixed(4)}`);
  }
  for (const [id, share] of Object.entries(preview.path_shares).filter(([k]) => !(k in preview.global_weights))) {
    const row = tree.locator("li").filter({ has: page.getByRole("button", { name: named(id), exact: true }) }).first();
    await expect(row).toContainText(`branch share ${share.toFixed(4)}`);
  }
}

test("the VC reference hierarchy, its raw ratings and its derived weights match the engine", async ({ page, request }, testInfo) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "b3-vc-browser"; p.title = "B3 reference weighting";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const before = await storedFile(request, p.id);
  const engine = await enginePreview(page, p, null);
  expect(engine.weights_ready).toBe(true);

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Weights");
  await expect(page.getByText(/Viewing: Default · stable ID/)).toBeVisible();

  // Every parent raw rating, and every parent local weight, as the engine computed them.
  for (const [id, raw] of Object.entries({ team: "100", problem_solution: "90", market: "80", traction: "70" })) {
    const name = at(p.criteria.filter((c) => c.id === id), 0).name;
    await expect(rating(page, name)).toHaveValue(raw);
    await expect(page.getByRole("table", { name: "Swing ratings under top level" }))
      .toContainText(at(Object.entries(engine.local_weights).filter(([k]) => k === id), 0)[1].toFixed(4));
  }
  // Every leaf raw rating and global weight.
  for (const [id, global] of Object.entries(engine.global_weights)) {
    const node = at(p.criteria.filter((c) => c.id === id), 0);
    const parent = at(p.criteria.filter((c) => c.id === node.parent_id), 0);
    const group = page.getByRole("table", { name: `Swing ratings under ${parent.name}` });
    await expect(rating(page, node.name)).toHaveValue(String(p.weight_profiles[0]?.judgements[id]));
    await expect(group).toContainText(global.toFixed(4));
    await expect(group).toContainText((engine.local_weights[id] ?? 0).toFixed(4));
  }
  await expectWeightsMatchEngine(page, p, engine);

  // Selecting a leaf explains its global weight with the engine's path shares.
  await page.getByRole("button", { name: "Founder Expertise", exact: true }).first().click();
  const derivation = page.getByLabel("Weight derivation for Founder Expertise");
  await expect(derivation).toContainText("Overall goal › Team › Founder Expertise");
  const steps = page.getByRole("table", { name: "Derivation steps for Founder Expertise" });
  await expect(steps).toContainText((engine.path_shares.team ?? 0).toFixed(4));          // 0.2941
  await expect(steps).toContainText((engine.local_weights.founder_expertise ?? 0).toFixed(4)); // 0.6061
  await expect(derivation).toContainText((engine.global_weights.founder_expertise ?? 0).toFixed(4)); // 0.1783
  await page.screenshot({ path: testInfo.outputPath("b3-vc-derivation.png"), fullPage: true });

  // Viewing and selecting changed nothing that is stored.
  await expect(saveState(page)).toHaveText("All changes saved");
  expect((await storedFile(request, p.id)).equals(before)).toBe(true);
  await request.delete(`/api/projects/${p.id}`);
});

test("a duplicated profile reproduces the reference results, then diverges alone", async ({ page, request }, testInfo) => {
  const p = readJson(VC_FILE) as Project;
  p.id = "b3-duplicate-browser"; p.title = "B3 duplicate profile";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Results");
  const reference = await readRanking(page);
  expect(reference.map((r) => r.value)).toEqual(["0.7227", "0.6599", "0.5986", "0.5734"]);

  await openTab(page, "Weights");
  await profileCommand(page, "Duplicate profile", { name: "Sensitivity review" });
  await expect(page.getByText(/Viewing: Sensitivity review · stable ID/)).toBeVisible();
  // The copy starts identical, so the documented ranking is unchanged.
  await openTab(page, "Results");
  expect(await readRanking(page)).toEqual(reference);

  // One raw judgement, changed in the copy only.
  await openTab(page, "Weights");
  await setRating(page, "Team", "10");
  const edited = await enginePreview(page, { ...p, weight_profiles: [...p.weight_profiles,
    { ...at(p.weight_profiles, 0), id: "sensitivity_review", name: "Sensitivity review",
      judgements: { ...at(p.weight_profiles, 0).judgements, team: 10 } }] }, "sensitivity_review");
  await expect(page.getByRole("table", { name: "Swing ratings under top level" }))
    .toContainText((edited.local_weights.team ?? 0).toFixed(4));
  await openTab(page, "Results");
  const changed = await readRanking(page);
  expect(changed).not.toEqual(reference);
  await page.screenshot({ path: testInfo.outputPath("b3-duplicated-profile.png"), fullPage: true });

  // Returning to the original profile restores its results exactly.
  await page.getByLabel("Weight profile", { exact: true }).selectOption("default");
  expect(await readRanking(page)).toEqual(reference);
  await expect(rating(page, "Team")).toHaveCount(0); // still on Results

  // Save and reopen keeps both profiles, with their own ratings.
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  await page.reload();
  await openTab(page, "Weights");
  await expect(rating(page, "Team")).toHaveValue("100");
  await page.getByLabel("Profile to edit").selectOption("sensitivity_review");
  await expect(rating(page, "Team")).toHaveValue("10");
  const reopened = readJson(resolve(REPO, "frontend", ".e2e-store", `${p.id}.json`)) as Project;
  expect(reopened.weight_profiles.map((x) => x.id)).toEqual(["default", "sensitivity_review"]);
  expect(at(reopened.weight_profiles, 0).judgements.team).toBe(100);
  expect(at(reopened.weight_profiles, 1).judgements.team).toBe(10);
  await request.delete(`/api/projects/${p.id}`);
});

test("profile management protects references and never silently substitutes a profile", async ({ page, request }, testInfo) => {
  const p = readJson(INFRA_FILE) as Project;
  p.id = "b3-infra-browser"; p.title = "B3 profile integrity";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Weights");

  // The deeper branch, the only child and the deliberate zero are all shown honestly.
  await expect(page.getByRole("table", { name: "Swing ratings under Reliability" })).toBeVisible();
  const delivery = page.getByRole("table", { name: "Swing ratings under Delivery capability" });
  await expect(delivery).toContainText("only item (weight 1)");
  await expect(delivery).toContainText("Not supplied; not required");
  const consent = page.getByRole("table", { name: "Swing ratings under Consent and community" });
  await expect(rating(page, "Ecological footprint")).toHaveValue("0");
  await expect(consent).toContainText("Zero rating");
  await expect(consent).toContainText("0.0000"); // a valid zero weight, not a missing one

  // Deleting the scenario-referenced profile requires an explicit replacement.
  await page.getByLabel("Profile to edit").selectOption("consent_led");
  await page.getByRole("button", { name: "Delete profile", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/Choose a replacement explicitly/);
  await expect(dialog.getByRole("button", { name: "Delete and replace references" })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("b3-delete-requires-replacement.png") });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  // Refused by the service too, so the rule is not merely a disabled button.
  const refused = await request.post("/api/edit", { data: { project: p, operations: [
    { op: "remove_weight_profile", profile_id: "consent_led" },
  ] } });
  expect(refused.status()).toBe(409);  // a refused model edit, not a schema error
  expect(JSON.stringify(await refused.json())).toContain("explicit replacement");

  await profileCommand(page, "Delete profile", { replacement: "default" });
  await expect(page.getByText(/Viewing: Balanced · stable ID/)).toBeVisible();
  await expect(page.getByLabel("Profile to edit")).not.toHaveValue("consent_led");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(saveState(page)).toHaveText("All changes saved");
  const saved = readJson(resolve(REPO, "frontend", ".e2e-store", `${p.id}.json`)) as Project;
  expect(saved.weight_profiles.map((x) => x.id)).toEqual(["default"]);
  expect(at(saved.scenarios, 0).weight_profile_id).toBe("default"); // updated, never dangling
  await expect(page.getByRole("button", { name: "Delete profile", exact: true })).toBeDisabled();

  // The GUI and a separate CLI process agree on the persisted file.
  const cli = cliEvaluate(resolve(REPO, "frontend", ".e2e-store", `${p.id}.json`)) as unknown as MavtResult;
  await openTab(page, "Results");
  const shown = await readRanking(page);
  expect(shown.map((r) => r.name)).toEqual(cli.ranking.map((r) => r.name));
  expect(shown.map((r) => r.value)).toEqual(cli.ranking.map((r) => r.value.toFixed(4)));
  await request.delete(`/api/projects/${p.id}`);
});

test("rapid profile switching never shows one profile's weights under another", async ({ page, request }) => {
  const p = readJson(INFRA_FILE) as Project;
  p.id = "b3-stale-browser"; p.title = "B3 stale responses";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  const balanced = await enginePreview(page, p, "default");
  const consent = await enginePreview(page, p, "consent_led");
  expect(balanced.global_weights.footprint).not.toBe(consent.global_weights.footprint);

  // Hold the first preview open, switch profile, then release the obsolete response.
  let release = (): void => undefined;
  const held = new Promise<void>((r) => { release = () => { r(); }; });
  let seen = 0;
  await page.route("**/api/weights/preview", async (route) => {
    if (++seen === 1) await held;
    await route.continue();
  });

  await page.goto(`/#/p/${p.id}`); await openTab(page, "Weights");
  await page.getByLabel("Profile to edit").selectOption("consent_led");
  release();
  await page.waitForLoadState("networkidle");
  const group = page.getByRole("table", { name: "Swing ratings under Consent and community" });
  await expect(group).toContainText((consent.global_weights.footprint ?? 0).toFixed(4));
  await expect(rating(page, "Ecological footprint")).toHaveValue("55");
  await expect(group).not.toContainText((balanced.global_weights.community ?? 0).toFixed(4));
  await expect(saveState(page)).toHaveText("All changes saved");
  await request.delete(`/api/projects/${p.id}`);
});

test("the weighting screen stays usable by keyboard and on a narrow window", async ({ page, request }, testInfo) => {
  const p = readJson(INFRA_FILE) as Project;
  p.id = "b3-narrow-browser"; p.title = "B3 narrow layout";
  expect((await request.post("/api/projects/import", { data: p })).status()).toBe(201);
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto(`/#/p/${p.id}`); await openTab(page, "Weights");

  // The stacked layout keeps the ratings, the swing cards and the legend reachable.
  const field = rating(page, "Capital cost");
  await field.scrollIntoViewIfNeeded();
  await expect(field).toBeVisible();
  await expect(page.locator(".swing-card").filter({ hasText: "Capital cost · stated swing" })).toBeVisible();
  // A decreasing cost criterion: the highest cost is the worst level, never the best.
  await expect(page.getByRole("region", { name: "Weight group Lifecycle cost" })
    .getByText(/Worst 100 → Best 40 NZD m/)).toBeVisible();
  await expect(page.getByText("Branch share", { exact: true })).toBeVisible(); // the legend entry
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("b3-narrow-layout.png"), fullPage: true });

  // A rating is edited entirely from the keyboard, and Escape abandons a draft without committing.
  await field.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("130");            // above 100: raw ratings are uncapped
  await page.keyboard.press("Enter");
  await expect(field).toHaveValue("130");
  await expect(saveState(page)).toHaveText(/Unsaved changes/);
  await field.press("ControlOrMeta+a");
  await page.keyboard.type("7");
  await page.keyboard.press("Escape");
  await expect(field).toHaveValue("130");

  // One completed edit is one undo step.
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(field).toHaveValue("100");
  await expect(saveState(page)).toHaveText("All changes saved");
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(field).toHaveValue("130");
  await request.delete(`/api/projects/${p.id}`);
});
