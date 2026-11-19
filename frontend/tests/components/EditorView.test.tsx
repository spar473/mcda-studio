import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { StarterMaterialization } from "../../src/api/types";
import type { EditorTab } from "../../src/model/issues";
import { EditorScreen } from "../../src/components/EditorScreen";
import { rememberWorkedEntry, chooseEditorView } from "../../src/state/viewMode";
import { doc, META, node, projectWith } from "../fixtures";

vi.mock("../../src/components/ResultsPanel", () => ({ ResultsPanel: ({ onOpenTab }: { onOpenTab: (tab: EditorTab) => void }) =>
  <section aria-label="Results"><p>Results content</p><button type="button" onClick={() => onOpenTab("classes")}>Open class setup</button></section> }));
vi.mock("../../src/components/EvidenceWorkspacePanel", () => ({ EvidenceWorkspacePanel: ({ active, renderWorkspace, onDirty }: {
  active: boolean; renderWorkspace: (node: React.ReactNode) => React.ReactNode; onDirty: (value: boolean) => void;
}) => {
  const [reviews, setReviews] = useState(0);
  return renderWorkspace(<section hidden={!active} aria-label="Owned review state">
    <p>Appended reviews: {reviews}</p><button type="button" onClick={() => { setReviews(value => value + 1); onDirty(true); }}>Append fixture review</button>
  </section>);
} }));
const analystTabs = ["Results", "Sensitivity", "Compare", "Reference cases", "Evidence", "Open Questions", "Decision"];
const project = projectWith([node("criterion")]);
function entry(fingerprint = "original") {
  rememberWorkedEntry({ project, receipt: { request: { mode: "worked_example", template_id: "venture_screening_study" }, project_fingerprint: fingerprint } } as StarterMaterialization);
}
beforeEach(() => {
  sessionStorage.clear(); Element.prototype.scrollIntoView = vi.fn();
  vi.spyOn(api, "getProject").mockResolvedValue(doc("original", project));
  vi.spyOn(api, "meta").mockResolvedValue(META);
  vi.spyOn(api, "starterTemplates").mockResolvedValue([]);
  vi.spyOn(api, "previewWeights").mockImplementation(() => new Promise(() => undefined));
  vi.spyOn(api, "validateAnalysis").mockImplementation(() => new Promise(() => undefined));
  vi.spyOn(api, "edit").mockResolvedValue(doc("original", project));
});
afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
const mount = () => render(<EditorScreen projectId={project.id} onClose={vi.fn()} onOpenOther={vi.fn()}/>);
const tabs = () => screen.getAllByRole("tab").map(tab => tab.textContent);

it("starts ordinary/imported projects in Builder, selects Results when hiding Model, and preserves the source and history", async () => {
  const original = structuredClone(project), edit = vi.mocked(api.edit), save = vi.spyOn(api, "saveProject");
  mount(); await screen.findByRole("tab", { name: "Model" });
  expect(screen.getByRole("tab", { name: "Model" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "Builder view" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Analyst view" }));
  expect(tabs()).toEqual(analystTabs); expect(screen.queryByRole("heading", { name: "Build" })).toBeNull();
  expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("button", { name: "Builder view" }));
  expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Model" })).toBeVisible();
  expect(screen.getByTestId("save-state")).toHaveTextContent("All changes saved");
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  await Promise.resolve();
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(original);
});
it("verifies the worked receipt fingerprint, overrides an old Builder choice and keeps the resulting session preference on reload", async () => {
  chooseEditorView(project.id, "builder"); entry();
  const first = mount(); await screen.findByText("Results content");
  expect(tabs()).toEqual(analystTabs);
  await waitFor(() => expect(sessionStorage.getItem(`mcda:worked-entry:${project.id}`)).toBeNull());
  expect(sessionStorage.getItem(`mcda:editor-view:${project.id}`)).toBe("analyst");
  first.unmount(); mount(); await screen.findByText("Results content"); expect(tabs()).toEqual(analystTabs);
});
it("refuses a mismatched gallery fingerprint and respects a valid explicit preference", async () => {
  chooseEditorView(project.id, "builder"); entry("another-source"); mount();
  await screen.findByRole("tab", { name: "Model" });
  expect(screen.getByRole("button", { name: "Builder view" })).toHaveAttribute("aria-pressed", "true");
});
it("reveals a requested Build repair tab and makes the mode change explicit", async () => {
  vi.mocked(api.validateAnalysis).mockImplementation((_project, configuration) => Promise.resolve({
    project_fingerprint: "original", configuration, weight_profile_id: null, scenario_id: null, validation: { issues: [] },
  }));
  chooseEditorView(project.id, "analyst"); mount(); await screen.findByText("Results content");
  expect(screen.queryByRole("tab", { name: "Classes" })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "Open class setup" }));
  expect(screen.getByRole("button", { name: "Builder view" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("tab", { name: "Classes" })).toHaveAttribute("aria-selected", "true");
});
it("keeps incomplete-model errors visible in Analyst and offers Builder without an edit", async () => {
  vi.mocked(api.getProject).mockResolvedValue(doc("original", project, [{ code: "MISSING_MEASUREMENT", severity: "error", message: "A measurement is missing.", path: "performances" }]));
  chooseEditorView(project.id, "analyst"); const edit = vi.spyOn(api, "edit"); mount();
  await screen.findByText("This model is incomplete —", { exact: false });
  expect(screen.getByText("A measurement is missing.", { exact: true })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "switch to Builder view to fix it" }));
  expect(screen.getByRole("button", { name: "Builder view" })).toHaveAttribute("aria-pressed", "true");
  expect(edit).not.toHaveBeenCalled();
});

it("retains the evidence workspace owner and dirty review state across both view switches", async () => {
  chooseEditorView(project.id, "analyst"); mount(); await screen.findByText("Results content");
  fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
  fireEvent.click(screen.getByRole("button", { name: "Append fixture review" }));
  expect(screen.getByText("Appended reviews: 1", { exact: true })).toBeVisible();
  for (const name of ["Builder view", "Analyst view"]) {
    fireEvent.click(screen.getByRole("button", { name }));
    expect(screen.getByText("Appended reviews: 1", { exact: true })).toBeVisible();
    expect(screen.getByTestId("save-state")).toHaveTextContent("Unsaved changes");
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  }
  expect(api.edit).not.toHaveBeenCalled();
});
