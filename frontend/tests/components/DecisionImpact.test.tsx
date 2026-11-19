import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { DecisionImpact } from "../../src/api/types";
import { QuestionsPanel } from "../../src/components/QuestionsPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const context = resolveContext(project, "fp", BASE_SELECTION);
const questions = { project_fingerprint: "fp", configuration: context.configuration,
  questions: [{ group: "blocking", code: "MISSING_MEASUREMENT", question: "What is the cost?", why: "Missing", evidence: "Collect it", alternative_id: "a", criterion_id: "cost", requirement_id: null, measurement_range: null }],
  coverage: ["Missing measurements"], limitations: [] };
function cell(over: Record<string, unknown>) {
  return { alternative_id: "a", alternative_name: "Option A", criterion_id: "cost", criterion_name: "Cost", current_label: "Good", ordered: true, global_weight: 0.5,
    effects: [], target_rank_labels: [], any_rank_labels: [], target_class_labels: [], leader_labels: [], smallest_changes: [], can_change_decision: false, tier: "none", reasons: [], ...over };
}
const impact = (cells: unknown[]): DecisionImpact => ({ project_fingerprint: "fp", configuration: context.configuration, weight_profile_id: null, scenario_id: null,
  status: "available", reason: "", label: "One cell at a time, everything else fixed.", baseline_leaders: ["a"], baseline_classes: {}, analysed_cells: cells.length,
  cells, limitations: ["Each cell is varied alone."] }) as unknown as DecisionImpact;
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }

it("is off by default: the new route is never called and Open Questions is unchanged", async () => {
  const open = vi.spyOn(api, "openQuestions").mockResolvedValue(questions as never);
  const route = vi.spyOn(api, "decisionImpact");
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await settle();
  expect(screen.getByText("What is the cost?")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Sort by decision impact" })).not.toBeChecked();
  expect(screen.queryByRole("region", { name: "Decision impact" })).toBeNull();
  expect(route).not.toHaveBeenCalled(); expect(open).toHaveBeenCalledTimes(1);
});

it("shows Python's order, labels and reasons in plain words when the toggle is on", async () => {
  vi.spyOn(api, "openQuestions").mockResolvedValue(questions as never);
  const route = vi.spyOn(api, "decisionImpact").mockResolvedValue(impact([
    cell({ tier: "leader_or_class", can_change_decision: true, leader_labels: ["Weak"], target_class_labels: ["Weak", "Fair"], target_rank_labels: ["Weak"], any_rank_labels: ["Weak"], smallest_changes: ["Fair"], reasons: ["judgement_only", "disputed"] }),
    cell({ alternative_id: "b", alternative_name: "Option B", tier: "none", current_label: "Fair", reasons: [] }),
  ]));
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await settle();
  fireEvent.click(screen.getByRole("checkbox", { name: "Sort by decision impact" }));
  await settle();
  expect(route).toHaveBeenCalledTimes(1);
  expect(route.mock.calls[0]?.[0]).toBe(project);
  const list = screen.getByRole("region", { name: "Decision impact" });
  const items = within(list).getAllByRole("listitem").filter(item => item.querySelector("strong"));
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("Could change the leader or a class");
  expect(items[0]).toHaveTextContent("Changes the leader: Weak");
  expect(items[0]).toHaveTextContent("Nearest label that changes something: Fair");
  expect(items[0]).toHaveTextContent("rests on judgement alone; disputed");
  expect(items[1]).toHaveTextContent("No other label changes a rank, the leader or a class");
  expect(items[1]).toHaveTextContent("No open reason");
  expect(screen.getByText("What is the cost?")).toBeInTheDocument();  // the question groups stay
  fireEvent.click(screen.getByRole("checkbox", { name: "Sort by decision impact" }));
  expect(screen.queryByRole("region", { name: "Decision impact" })).toBeNull();
});

it("rejects a response for another revision, offers a retry and shows an unavailable reason", async () => {
  vi.spyOn(api, "openQuestions").mockResolvedValue(questions as never);
  const route = vi.spyOn(api, "decisionImpact")
    .mockResolvedValueOnce({ ...impact([]), project_fingerprint: "old" })
    .mockResolvedValue({ ...impact([]), status: "unavailable", reason: "Decision impact unavailable: 1 measurement(s) are missing." });
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await settle();
  fireEvent.click(screen.getByRole("checkbox", { name: "Sort by decision impact" }));
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match");
  fireEvent.click(screen.getByRole("button", { name: "Retry decision impact" }));
  await settle();
  expect(screen.getByRole("status")).toHaveTextContent("measurement(s) are missing");
  expect(route).toHaveBeenCalledTimes(2);
});
