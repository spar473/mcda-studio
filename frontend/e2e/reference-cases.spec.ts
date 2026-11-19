import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import type { ProjectDocument, ReferenceCasesResult } from "../src/api/types";
import { openTab, readJson, REPO, saveState, storedFile } from "./helpers";

const id = "nz_first_round_retrospective";
const SET = resolve(REPO, "examples", "nz_first_round_retrospective", "reference-cases.json");

test("the reference cases example: Vertus Energy's cards, its own case left out on request, outcomes only on request, nothing changes", async ({ page, request }) => {
  test.setTimeout(120_000);
  await request.delete(`/api/projects/${id}`);
  expect((await request.post(`/api/examples/${id}/import`)).status()).toBe(201);
  const snapshot = async () => {
    const response = await request.get(`/api/projects/${id}`);
    return { body: await response.json() as ProjectDocument, etag: response.headers().etag, file: await storedFile(request, id) };
  };
  const before = await snapshot();
  const writes: string[] = [];
  page.on("request", value => {
    if (value.url().endsWith("/api/edit") || ["PUT", "DELETE"].includes(value.method()) && value.url().includes(`/api/projects/${id}`)) writes.push(value.url());
  });
  await page.goto(`/#/p/${id}`);
  await page.getByRole("button", { name: "Analyst view", exact: true }).click();
  await openTab(page, "Reference cases");
  const panel = page.getByRole("region", { name: "Reference cases", exact: true });
  await expect(panel.getByText("No reference set is open.")).toBeVisible();
  await panel.getByLabel("Open a reference-cases file").setInputFiles(SET);
  await panel.getByRole("combobox", { name: "Alternative" }).selectOption({ label: "Vertus Energy" });
  const expected = await (await request.post("/api/reference-cases", { data: {
    project: before.body.project, reference_cases: readJson(SET), alternative_id: "vertus_energy" } })).json() as ReferenceCasesResult;
  const cards = panel.getByRole("list", { name: "Most similar reference cases for Vertus Energy" }).getByRole("article");
  await expect(cards).toHaveCount(3);
  const names = expected.alternatives[0]?.cases.map(c => c.name) ?? [];
  expect(names).toHaveLength(3);
  expect(names[0]).toBe("Vertus Energy");  // the self-match, before leaving it out
  for (const [index, name] of names.entries()) await expect(cards.nth(index).getByRole("heading", { level: 4 })).toHaveText(name);
  await expect(panel.getByText(/says nothing about how this alternative will turn out/)).toBeVisible();
  const leftOut = page.waitForResponse(value => value.url().endsWith("/api/reference-cases") && (value.request().postDataJSON() as { exclude_same_id?: boolean } | null)?.exclude_same_id === true);
  await panel.getByRole("checkbox", { name: "Leave out this alternative's own case", exact: true }).check();
  const others = await (await leftOut).json() as ReferenceCasesResult;
  expect(others.alternatives[0]?.excluded_case_ids).toEqual(["vertus_energy"]);
  const otherNames = others.alternatives[0]?.cases.map(c => c.name) ?? [];
  expect(otherNames).toHaveLength(3);
  expect(otherNames).not.toContain("Vertus Energy");
  for (const [index, name] of otherNames.entries()) await expect(cards.nth(index).getByRole("heading", { level: 4 })).toHaveText(name);
  await expect(panel.getByText("Vertus Energy's own reference case is left out of this comparison.")).toBeVisible();
  await expect(panel.getByText("What happened next", { exact: true })).toHaveCount(0);
  const withOutcomes = page.waitForResponse(value => value.url().endsWith("/api/reference-cases") && (value.request().postDataJSON() as { include_outcomes?: boolean; exclude_same_id?: boolean } | null)?.include_outcomes === true);
  await panel.getByRole("checkbox", { name: "Show what happened next", exact: true }).check();
  const shown = await (await withOutcomes).json() as ReferenceCasesResult;
  const outcome = shown.alternatives[0]?.cases[0]?.outcome;
  expect(outcome?.as_of).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await expect(cards.first().getByRole("region", { name: /^What happened next for / })).toContainText(`as of ${outcome?.as_of ?? ""}`);
  expect(writes).toEqual([]);
  const after = await snapshot();
  expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
  await expect(saveState(page)).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});
