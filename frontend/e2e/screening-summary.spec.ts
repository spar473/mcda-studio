// The screening summary on the venture study in the real application: it leads Results above the
// fold at 1440 × 900, shows Hnry's mandate failure beside its rank, follows the selected profile,
// matches the engine's own exact sensitivity for the leader's closest change, and appears in the
// presentation view. Nothing here edits the project.
import { expect, test, type Locator } from "@playwright/test";
import { resolve } from "node:path";
import type { Project, ScreeningSummary } from "../src/api/types";
import { openTab, readJson, REPO } from "./helpers";

const FILE = resolve(REPO, "examples", "nz_venture_screening", "project.json");
const row = (table: Locator, name: string) =>
  table.getByRole("row").filter({ has: table.page().getByRole("rowheader", { name, exact: true }) });

test("screening summary: above the fold, mandate beside rank, profile-aware and exact", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const project = readJson(FILE) as Project;
  const imported = await request.post("/api/projects/import", { data: project });
  expect([201, 409]).toContain(imported.status());
  const before = (await (await request.get(`/api/projects/${project.id}`)).json() as { fingerprint: string }).fingerprint;
  await page.goto(`/#/p/${project.id}`);
  await openTab(page, "Results");

  const table = page.getByRole("table", { name: "Screening summary" });
  await expect(table).toBeVisible();
  const box = await table.boundingBox();
  expect(box && box.y).toBeLessThan(900);
  await expect(table.getByRole("rowheader")).toHaveText([
    "Upstock", "Wellumio", "Hectre", "Wych", "Captivate Technology", "Scentian Bio", "Hnry", "Kea Aerospace",
  ]);
  await expect(row(table, "Hnry")).toContainText("Fails: Stage at most Series A");
  await expect(row(table, "Upstock")).toContainText("Prioritise for diligence");

  // The leader's closest change equals the engine's exact class change on that criterion.
  const configuration = { method: "mavt_sorting", weight_profile_id: null, scenario_id: null, parameters: {} };
  const summary = await (await request.post("/api/screening-summary", { data: { project, configuration } })).json() as ScreeningSummary;
  const leader = summary.rows[0]?.fragility;
  if (!leader?.criterion_id || leader.local_weight == null) throw new Error("expected a closest change for the leader");
  const sweep = await (await request.post("/api/sensitivity", { data: { project, configuration, node_id: leader.criterion_id, steps: 2 } })).json() as
    { class_changes: { alternative_id: string; first_change_up: { weight: number } | null; first_change_down: { weight: number } | null }[] };
  const upstock = sweep.class_changes.find((c) => c.alternative_id === "upstock");
  const exact = leader.direction === "raise" ? upstock?.first_change_up?.weight : upstock?.first_change_down?.weight;
  expect(exact).toBe(leader.local_weight);

  // Switching profile re-reads the summary for that profile.
  await page.getByLabel("Weight profile", { exact: true }).selectOption("commercial_traction");
  await expect(row(table, "Hectre")).toContainText("Monitor (0.0009)");
  await expect(table.getByRole("rowheader")).toHaveText([
    "Upstock", "Hectre", "Wych", "Hnry", "Wellumio", "Captivate Technology", "Scentian Bio", "Kea Aerospace",
  ]);

  // The presentation view reads the same summary.
  await openTab(page, "Model");
  await page.getByRole("button", { name: "Present", exact: true }).click();
  const shown = page.getByRole("table", { name: "Screening summary" });
  await expect(shown).toBeVisible();
  const presented = await shown.boundingBox();
  expect(presented && presented.y).toBeLessThan(900); // above the diagram, so above the fold
  await page.getByRole("button", { name: "Exit presentation", exact: true }).click();

  const after = (await (await request.get(`/api/projects/${project.id}`)).json() as { fingerprint: string }).fingerprint;
  expect(after).toBe(before);
});
