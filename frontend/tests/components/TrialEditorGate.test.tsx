import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import { EditorScreen } from "../../src/components/EditorScreen";
import type { WeightTrial } from "../../src/state/useWeightTrial";
import { chooseEditorView } from "../../src/state/viewMode";
import { doc, META, node, projectWith } from "../fixtures";

vi.mock("../../src/components/ResultsPanel", () => ({ ResultsPanel: ({ weightTrial: trial }: { weightTrial: WeightTrial }) => <section>
  <button type="button" onClick={() => trial.acceptBaseline([{ criterion_id: "criterion", name: "Criterion", raw_rating: 100, local_weight: 1, global_share: 1, slider_min: 0, slider_max: 100, step: "any" }])}>Prepare fixture controls</button>
  <button type="button" onClick={() => trial.change("criterion", 12.3456789012345)}>Start fixture trial</button>
  <button type="button" onClick={trial.reset}>Reset fixture trial</button>
</section> }));
vi.mock("../../src/components/SensitivityPanel", () => ({ SensitivityPanel: () => <p>Saved sensitivity fixture</p> }));
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it("blocks Sensitivity across tab and view changes until Reset without edits, saves, history or loss of trial ownership", async () => {
  const project = projectWith([node("criterion")]), before = structuredClone(project);
  Element.prototype.scrollIntoView = vi.fn(); sessionStorage.clear(); chooseEditorView(project.id, "analyst");
  vi.spyOn(api, "getProject").mockResolvedValue(doc("original", project)); vi.spyOn(api, "meta").mockResolvedValue(META);
  vi.spyOn(api, "starterTemplates").mockResolvedValue([]); vi.spyOn(api, "previewWeights").mockImplementation(() => new Promise(() => undefined));
  vi.spyOn(api, "validateAnalysis").mockImplementation((_source, configuration) => Promise.resolve({
    project_fingerprint: "original", configuration, weight_profile_id: null, scenario_id: null, validation: { issues: [] },
  }));
  const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject");
  render(<EditorScreen projectId={project.id} onClose={vi.fn()} onOpenOther={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", { name: "Prepare fixture controls" }));
  fireEvent.click(screen.getByRole("button", { name: "Start fixture trial" }));
  fireEvent.click(screen.getByRole("tab", { name: "Sensitivity" }));
  expect(screen.getByText("Reset what-if to use this", { exact: true })).toBeVisible(); expect(screen.queryByText("Saved sensitivity fixture")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Builder view" }));
  expect(screen.getByText("Reset what-if to use this", { exact: true })).toBeVisible();
  fireEvent.click(screen.getByRole("tab", { name: "Results" }));
  fireEvent.click(await screen.findByRole("button", { name: "Reset fixture trial" }));
  fireEvent.click(screen.getByRole("tab", { name: "Sensitivity" }));
  await waitFor(() => expect(screen.getByText("Saved sensitivity fixture")).toBeVisible());
  expect(screen.getByTestId("save-state")).toHaveTextContent("All changes saved"); expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
});
