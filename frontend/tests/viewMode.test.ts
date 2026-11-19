import { afterEach, expect, it, vi } from "vitest";
import type { StarterMaterialization } from "../src/api/types";
import { ANALYST_STARTERS, chooseEditorView, consumeWorkedEntry, rememberWorkedEntry, viewIntent } from "../src/state/viewMode";

afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
const receipt = (template = "venture_screening_study", mode = "worked_example") => ({
  project: { id: "study" }, receipt: { request: { template_id: template, mode }, project_fingerprint: "exact-source" },
}) as StarterMaterialization;
it("defaults ordinary projects and direct imports to Builder, scopes explicit choices by project and browser session", () => {
  expect(viewIntent("study")).toEqual({ view: "builder", preference: "builder", entry: null });
  chooseEditorView("study", "analyst");
  expect(viewIntent("study").view).toBe("analyst"); expect(viewIntent("another").view).toBe("builder");
  chooseEditorView("study", "builder"); expect(viewIntent("study").view).toBe("builder");
  sessionStorage.clear(); expect(viewIntent("study").view).toBe("builder");
});
it("uses only the real worked study receipt and retains its exact fingerprint for editor verification", () => {
  chooseEditorView("study", "builder"); rememberWorkedEntry(receipt());
  expect(viewIntent("study")).toEqual({ view: "analyst", preference: "builder", entry: {
    projectId: "study", templateId: "venture_screening_study", fingerprint: "exact-source",
  } });
  consumeWorkedEntry("study"); expect(viewIntent("study").entry).toBeNull();
  rememberWorkedEntry(receipt("venture_screening")); expect(viewIntent("study").view).toBe("builder");
  rememberWorkedEntry(receipt("venture_screening_study", "fresh")); expect(viewIntent("study").view).toBe("builder");
});
it("ignores malformed or mismatched gallery hints while retaining a valid explicit choice", () => {
  chooseEditorView("study", "analyst");
  for (const text of ["{bad JSON", JSON.stringify({ projectId: "other", fingerprint: "fp", templateId: "venture_screening_study" }), JSON.stringify({ projectId: "study", fingerprint: 12, templateId: "venture_screening_study" })]) {
    sessionStorage.setItem("mcda:worked-entry:study", text);
    expect(viewIntent("study")).toEqual({ view: "analyst", preference: "analyst", entry: null });
  }
});
it("keeps a working Builder default if session storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw Error("storage denied"); });
  expect(viewIntent("study")).toEqual({ view: "builder", preference: "builder", entry: null });
});
it("opens every listed worked-example starter in the Analyst view, and no other starter", () => {
  expect([...ANALYST_STARTERS].sort()).toEqual([
    "clinic_site_selection", "engineering_trade_study", "flood_defence_options", "venture_screening_study",
  ]);
  for (const id of ANALYST_STARTERS) {
    sessionStorage.clear(); rememberWorkedEntry(receipt(id));
    expect(viewIntent("study")).toEqual({ view: "analyst", preference: "builder", entry: { projectId: "study", templateId: id, fingerprint: "exact-source" } });
    sessionStorage.clear(); rememberWorkedEntry(receipt(id, "fresh"));
    expect(sessionStorage.getItem("mcda:worked-entry:study")).toBeNull();
    expect(viewIntent("study")).toEqual({ view: "builder", preference: "builder", entry: null });
  }
  for (const id of ["blank", "supplier_selection", "infrastructure_procurement", "venture_screening", "unknown"]) {
    sessionStorage.clear(); rememberWorkedEntry(receipt(id));
    expect(sessionStorage.getItem("mcda:worked-entry:study")).toBeNull();
    expect(viewIntent("study")).toEqual({ view: "builder", preference: "builder", entry: null });
  }
});
it("keeps the stored starter and ignores a stored hint whose starter is not listed or not text", () => {
  chooseEditorView("study", "builder");
  for (const templateId of ["supplier_selection", "venture_screening", 7, null]) {
    sessionStorage.setItem("mcda:worked-entry:study", JSON.stringify({ projectId: "study", fingerprint: "fp", templateId }));
    expect(viewIntent("study")).toEqual({ view: "builder", preference: "builder", entry: null });
  }
  sessionStorage.setItem("mcda:worked-entry:study", JSON.stringify({ projectId: "study", fingerprint: "fp", templateId: "flood_defence_options" }));
  expect(viewIntent("study").entry).toEqual({ projectId: "study", fingerprint: "fp", templateId: "flood_defence_options" });
});
