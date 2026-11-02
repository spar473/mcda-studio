import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import { QuestionsPanel } from "../../src/components/QuestionsPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

it("shows actionable grouped questions and limitations without editing the project", async () => {
  const context = resolveContext(project, "fp", BASE_SELECTION);
  const open = vi.fn();
  vi.spyOn(api, "openQuestions").mockResolvedValue({ project_fingerprint: "fp", configuration: context.configuration,
    questions: [{ group: "blocking", code: "MISSING_MEASUREMENT", question: "What is the cost?", why: "Missing", evidence: "Collect it", alternative_id: "a", criterion_id: "cost", requirement_id: null, measurement_range: null }],
    coverage: ["Missing measurements"], limitations: ["Other signals are not assessed."] });
  render(<QuestionsPanel project={project} context={context} onOpenTab={open}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  expect(screen.getByText("What is the cost?")).toBeInTheDocument();
  expect(screen.getByLabelText("Questions limitations")).toHaveTextContent("Other signals are not assessed.");
  fireEvent.click(screen.getByRole("button", { name: "Open measurements" }));
  expect(open).toHaveBeenCalledWith("measurements");
});

it("rejects a response for another revision and retries the current request", async () => {
  const context = resolveContext(project, "fp", BASE_SELECTION);
  const body = { project_fingerprint: "fp", configuration: context.configuration,
    questions: [], coverage: [], limitations: ["Not all signals are assessed."] };
  const spy = vi.spyOn(api, "openQuestions")
    .mockResolvedValueOnce({ ...body, project_fingerprint: "old" }).mockResolvedValue(body);
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  expect(screen.getByRole("alert")).toHaveTextContent("do not match");
  fireEvent.click(screen.getByRole("button", { name: "Retry questions" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  expect(screen.getByLabelText("Questions limitations")).toHaveTextContent("Not all signals");
  expect(spy).toHaveBeenCalledTimes(2);
});

it("keeps the SMAA heuristic label and routes new signals to their editors", async () => {
  const context = resolveContext(project, "fp", BASE_SELECTION);
  const open = vi.fn();
  vi.spyOn(api, "openQuestions").mockResolvedValue({ project_fingerprint: "fp", configuration: context.configuration,
    questions: [
      { group: "decision_sensitive", code: "WEIGHT_CLASS_CHANGE", question: "Could a class change?", why: "Boundary", evidence: "Review", alternative_id: "a", criterion_id: "cost", requirement_id: null, measurement_range: null },
      { group: "decision_sensitive", code: "SMAA_INPUT_TO_CHECK", question: "What supports this input?", why: "heuristic: association in these draws, not causation or value of information", evidence: "Review uncertainty", alternative_id: null, criterion_id: null, requirement_id: null, measurement_range: null },
    ], coverage: ["Class sensitivity", "SMAA-2 heuristic"], limitations: [] });
  render(<QuestionsPanel project={project} context={context} onOpenTab={open}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  expect(screen.getByText(/heuristic: association/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open classes" }));
  expect(open).toHaveBeenLastCalledWith("classes");
  fireEvent.click(screen.getByRole("button", { name: "Open uncertainty" }));
  expect(open).toHaveBeenLastCalledWith("uncertainty");
});

it("loads a local dossier and sends it only with the current request", async () => {
  const context = resolveContext(project, "fp", BASE_SELECTION);
  const body = { project_fingerprint: "fp", configuration: context.configuration,
    questions: [], coverage: [], limitations: [] };
  const spy = vi.spyOn(api, "openQuestions").mockResolvedValue(body);
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  const file = new File(["{}"], "evidence.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve('{"schema_version":1}') });
  await act(async () => { fireEvent.change(screen.getByLabelText("Evidence dossier (optional)"), { target: { files: [file] } }); await Promise.resolve(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  expect(spy).toHaveBeenLastCalledWith(project, context.configuration, expect.any(AbortSignal), { schema_version: 1 });
  expect(screen.getByText(/selecting a dossier does not accept its claims/)).toBeInTheDocument();
});

it("explains range witnesses separately from boundary contacts", async () => {
  const context = resolveContext(project, "fp", BASE_SELECTION);
  vi.spyOn(api, "openQuestions").mockResolvedValue({ project_fingerprint: "fp", configuration: context.configuration,
    questions: [{ group: "decision_sensitive", code: "MEASUREMENT_RANGE_CHANGE", question: "Check the stated cost range?", why: "Its rank can change.", evidence: "Review the source.", alternative_id: "a", criterion_id: "cost", requirement_id: null,
      measurement_range: { alternative_id: "a", criterion_id: "cost", lower: 0, upper: 1, baseline_rank: 1, rank_can_change: true, baseline_class_id: null, class_can_change: null, minimum_score_at: 0, maximum_score_at: 1,
        boundary_contacts: [{ kind: "rank", reference_id: "b", lower: 0.5, upper: 0.5, exact_lower: "1/2", exact_upper: "1/2", score_threshold: 0.5 }],
        witnesses: [{ measurement: 0, score: 0, rank: 2, class_id: null }, { measurement: 1, score: 1, rank: 1, class_id: null }], limitations: ["Only this cell varies."] } }],
    coverage: ["Measurement ranges"], limitations: [] });
  render(<QuestionsPanel project={project} context={context} onOpenTab={vi.fn()}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  fireEvent.click(screen.getByText("Measurement range analysis"));
  expect(screen.getByLabelText("Range witnesses")).toHaveTextContent("rank 2");
  expect(screen.getByLabelText("Range boundary contacts")).toHaveTextContent("Rank comparison with b");
  expect(screen.getByText(/not a probability distribution/)).toBeInTheDocument();
});
