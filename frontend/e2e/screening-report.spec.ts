import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { ProjectDocument } from "../src/api/types";
import { openTab, saveState, storedFile } from "./helpers";
const id = "nz_venture_screening_study";
async function gallery(page: Page) {
  await page.goto("/"); await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click();
  await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
}
async function snapshot(request: APIRequestContext) {
  const response = await request.get(`/api/projects/${id}`);
  return { body: await response.json() as ProjectDocument, etag: response.headers().etag, file: await storedFile(request, id) };
}
async function report(page: Page) {
  const pending = page.waitForEvent("download"); await page.getByRole("button", { name: "Download screening report", exact: true }).click();
  const download = await pending, path = await download.path(); if (!path) throw Error("Download missing");
  return { name: download.suggestedFilename(), text: readFileSync(path, "utf8") };
}

test("the Analyst view downloads one self-contained report, is blocked during a what-if trial, and never changes the study", async ({ page, request }) => {
  test.setTimeout(120_000); await gallery(page);
  const before = await snapshot(request), writes: string[] = [];
  page.on("request", value => { if (value.url().endsWith("/api/edit") || ["PUT", "DELETE"].includes(value.method()) && value.url().includes(`/api/projects/${id}`)) writes.push(value.url()); });
  const first = await report(page);
  expect(first.name).toBe("screening-report.html");
  expect(first.text.startsWith("<!doctype html>")).toBe(true);
  for (const text of ["Venture screening: NZ startups", "Technical/IP-led", "Commercial/traction-led", "This report supports a screening decision.", "not investment advice, not a prediction of success", "Fails: Stage at most Series A", "Profile comparison", "No evidence dossier was supplied."]) expect(first.text).toContain(text);
  expect(first.text).not.toMatch(/<script|<link|<img|\bsrc=|\bhref=|@import|url\(/i);
  expect(first.text).not.toContain("Generated on");
  expect(first.text).toContain(before.body.fingerprint);
  // With the study's evidence open, the same button carries it into the report.
  await openTab(page, "Evidence"); await page.getByRole("button", { name: "Open the study's evidence", exact: true }).click();
  await expect(page.getByLabel("Evidence claims", { exact: true })).toBeVisible(); await openTab(page, "Results");
  const withEvidence = await report(page);
  expect(withEvidence.text).toContain("Judgement-only ratings: 71 of 128"); expect(withEvidence.text).toContain("Claims: 154");
  // A what-if trial blocks the download with the same Reset message as every other download.
  await page.getByText("What-if weights", { exact: true }).click();
  await expect(page.getByRole("slider", { name: "What-if Team", exact: true })).toBeVisible();
  await page.getByRole("slider", { name: "What-if Team", exact: true }).focus(); await page.keyboard.press("Home");
  await expect(page.getByRole("button", { name: "Download screening report", exact: true })).toBeDisabled();
  await expect(page.getByText("Reset what-if to download the saved model", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByRole("button", { name: "Download screening report", exact: true })).toBeEnabled();
  expect((await report(page)).text).toBe(withEvidence.text);  // Reset restores the exact saved report
  const after = await snapshot(request);
  expect(after.body).toEqual(before.body); expect(after.etag).toBe(before.etag); expect(after.file.equals(before.file)).toBe(true);
  expect(writes).toEqual([]);
  await expect(saveState(page)).toHaveText("All changes saved"); await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
});
