import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../../src/api/client";
import type { ReferenceCasesResult, ReferenceCasesValidation } from "../../src/api/types";
import { ReferenceCasesPanel } from "../../src/components/ReferenceCasesPanel";
import { canonical } from "../../src/state/analysisContext";
import { context, project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }

const SET = { kind: "reference-cases", version: 1, id: "set", title: "Set", criteria_from: "p1", cases: [], sources: {} };
const valid: ReferenceCasesValidation = { reference_set_id: "set", valid: true, issues: [], case_count: 4, rating_count: 20 };

function leaf(id: string, over: Record<string, unknown> = {}) {
  return { criterion_id: id, criterion_name: id.toUpperCase(), ordered: true, alternative_label: "Low", case_label: "Low",
    steps: 0, gap: "0/1", missing: null, case_note: "", ...over };
}
function match(id: string, name: string, similarity: number, exact: string) {
  return { case_id: id, name, snapshot_date: "2021-10-27", context: [{ label: "First round", value: `Round of ${name}` }],
    similarity, similarity_exact: exact, shared_count: 3, compared_count: 4,
    same: [leaf("same1")], one_step: [leaf("near", { case_label: "Mid", steps: 1, gap: "1/3" })],
    further: [leaf("cat", { ordered: false, case_label: "Blue", alternative_label: "Red", steps: null, gap: "1/1" })],
    not_compared: [leaf("gone", { alternative_label: null, case_label: null, steps: null, gap: null, missing: "reference_case" })],
    outcome: null as null | Record<string, unknown> };
}
function result(includeOutcomes: boolean, excludeSameId = false): ReferenceCasesResult {
  const cases = [match("second", "Second Co", 0.75, "3/4"), match("first", "First Co", 0.5, "1/2"), match("third", "Third Co", 0.25, "1/4")];
  if (includeOutcomes) cases.forEach((c, i) => { c.outcome = { label: `Outcome ${String(i)}`, as_of: `2024-06-2${String(i)}`, note: "A note.", claim_ids: [] }; });
  return { project_fingerprint: "fp", reference_set_id: "set", reference_set_title: "Set", configuration: context.configuration,
    weight_profile_id: "first", status: "available", reason: "", k: 3, weighting: "equal", min_shared_fraction: "1/2",
    include_outcomes: includeOutcomes, exclude_same_id: excludeSameId, compared_criteria: ["same1", "near", "cat", "gone"],
    alternatives: [{ alternative_id: "c", alternative_name: "Alt C", cases, remaining_count: 0,
      not_comparable: [{ case_id: "thin", name: "Thin Co", snapshot_date: "2020-09-21", shared_count: 1, compared_count: 4, shared_fraction: "1/4" }],
      excluded_case_ids: excludeSameId ? ["c"] : [] }],
    label: "Similarity is measured only on the rated criteria. It says nothing about how this alternative will turn out.",
    limitations: ["Numeric criteria are not compared in version 1 of the reference set."] } as unknown as ReferenceCasesResult;
}

async function open(text = JSON.stringify(SET)) {
  const file = new File([text], "reference-cases.json");
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  fireEvent.change(screen.getByLabelText("Open a reference-cases file"), { target: { files: [file] } });
  await settle(); await settle(); await settle();
}

it("calls nothing until a file is opened, then draws the engine's three cards in its order", async () => {
  const check = vi.spyOn(api, "validateReferenceCases").mockResolvedValue(valid);
  const route = vi.spyOn(api, "referenceCases").mockImplementation((...args) => Promise.resolve(result(args[4])));
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await settle();
  expect(screen.getByText("No reference set is open.")).toBeInTheDocument();
  expect(check).not.toHaveBeenCalled(); expect(route).not.toHaveBeenCalled();
  await open();
  expect(check).toHaveBeenCalledTimes(1);
  expect(route).toHaveBeenCalledTimes(1);
  expect(route.mock.calls[0]?.[3]).toBe("c");  // the first alternative
  expect(route.mock.calls[0]?.[4]).toBe(false);
  const cards = within(screen.getByRole("list", { name: "Most similar reference cases for Alt C" })).getAllByRole("article");
  expect(cards.map(card => within(card).getByRole("heading", { level: 4 }).textContent)).toEqual(["Second Co", "First Co", "Third Co"]);
  expect(cards[0]).toHaveTextContent("Snapshot 2021-10-27");
  expect(cards[0]).toHaveTextContent("Round of Second Co");
  expect(cards[0]).toHaveTextContent("Similarity 0.7500");
  expect(cards[0]).toHaveTextContent("3 of 4 compared criteria rated on both sides");
  fireEvent.click(screen.getByRole("button", { name: "Similarity details for Second Co" }));
  expect(screen.getByText(/Exact similarity 3\/4\./)).toBeInTheDocument();
  expect(screen.getByText(/says nothing about how this alternative will turn out/)).toBeInTheDocument();
  const first = cards[0];
  if (!first) throw Error("no card");
  expect(within(first).getByRole("region", { name: "Same label for Second Co" })).toHaveTextContent("SAME1: Low");
  expect(within(first).getByRole("region", { name: "One step apart for Second Co" })).toHaveTextContent("NEAR: Low here, Mid then (1 step)");
  expect(within(first).getByRole("region", { name: "Further apart for Second Co" })).toHaveTextContent("CAT: Red here, Blue then");
  expect(within(first).getByRole("region", { name: "Not compared for Second Co" })).toHaveTextContent("GONE: not rated for this case");
  expect(screen.getByRole("region", { name: "Not comparable reference cases" })).toHaveTextContent("Thin Co (snapshot 2020-09-21): 1 of 4 compared criteria rated on both sides");
  expect(screen.queryByText("What happened next")).toBeNull();
});

it("shows what happened next only when the switch is on, by asking Python again", async () => {
  vi.spyOn(api, "validateReferenceCases").mockResolvedValue(valid);
  const route = vi.spyOn(api, "referenceCases").mockImplementation((...args) => Promise.resolve(result(args[4])));
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await open();
  const toggle = screen.getByRole("checkbox", { name: "Show what happened next" });
  expect(toggle).not.toBeChecked();
  expect(screen.queryByText(/Outcome 0/)).toBeNull();
  fireEvent.click(toggle); await settle(); await settle();
  expect(route).toHaveBeenCalledTimes(2);
  expect(route.mock.calls[1]?.[4]).toBe(true);
  const outcome = screen.getByRole("region", { name: "What happened next for Second Co" });
  expect(outcome).toHaveTextContent("Outcome 0");
  expect(outcome).toHaveTextContent("as of 2024-06-20");
  expect(outcome).toHaveTextContent("A note.");
  fireEvent.click(toggle); await settle(); await settle();
  expect(screen.queryByRole("region", { name: "What happened next for Second Co" })).toBeNull();
});

it("leaves out the alternative's own case only when that switch is on, by asking Python again", async () => {
  vi.spyOn(api, "validateReferenceCases").mockResolvedValue(valid);
  const route = vi.spyOn(api, "referenceCases").mockImplementation((...args) => Promise.resolve(result(args[4], args[5])));
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await open();
  const toggle = screen.getByRole("checkbox", { name: "Leave out this alternative's own case" });
  expect(toggle).not.toBeChecked();
  expect(route.mock.calls[0]?.[5]).toBe(false);
  expect(screen.queryByText(/own reference case is left out/)).toBeNull();
  fireEvent.click(toggle); await settle(); await settle();
  expect(route).toHaveBeenCalledTimes(2);
  expect(route.mock.calls[1]?.[5]).toBe(true);
  expect(route.mock.calls[1]?.[4]).toBe(false);
  expect(screen.getByText("Alt C's own reference case is left out of this comparison.")).toBeInTheDocument();
  fireEvent.click(toggle); await settle(); await settle();
  expect(route.mock.calls[2]?.[5]).toBe(false);
  expect(screen.queryByText(/own reference case is left out/)).toBeNull();
});

it("shows the engine's validation messages for a bad file and never runs the analysis", async () => {
  vi.spyOn(api, "validateReferenceCases").mockResolvedValue({ ...valid, valid: false,
    issues: [{ severity: "error", code: "REFERENCE_SOURCE_AFTER_SNAPSHOT", path: "cases[0].ratings[1].claim_ids[0]",
      message: "claim 'c1' rests on source 'late' dated 2021-10-28, after the snapshot 2021-10-27" }] });
  const route = vi.spyOn(api, "referenceCases");
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await open();
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("cannot be used with this project (1 problem)");
  expect(alert).toHaveTextContent("cases[0].ratings[1].claim_ids[0]");
  expect(alert).toHaveTextContent("after the snapshot 2021-10-27");
  expect(route).not.toHaveBeenCalled();
});

it("shows a refused file's server message, an unreadable file, and an unavailable result", async () => {
  const check = vi.spyOn(api, "validateReferenceCases")
    .mockRejectedValueOnce(new ApiError(422, "INVALID_REQUEST", "reference-cases version 2 is not supported"))
    .mockResolvedValue(valid);
  const route = vi.spyOn(api, "referenceCases").mockResolvedValue({ ...result(false), status: "unavailable", reason: "Reference cases unavailable: the project has no weight profile.", alternatives: [] });
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await open();
  expect(screen.getByRole("alert")).toHaveTextContent("version 2 is not supported");
  fireEvent.click(screen.getByRole("button", { name: "Retry the check" })); await settle(); await settle(); await settle();
  expect(check).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("status")).toHaveTextContent("no weight profile");
  expect(route).toHaveBeenCalledTimes(1);
  await open("{not json");
  expect(screen.getByRole("alert")).toHaveTextContent("Could not read the reference-cases file as JSON.");
});

it("opening, switching and choosing another alternative are view-only", async () => {
  const before = canonical(project);
  vi.spyOn(api, "validateReferenceCases").mockResolvedValue(valid);
  const route = vi.spyOn(api, "referenceCases").mockImplementation((...args) => Promise.resolve(result(args[4])));
  const others = Object.keys(api)
    .filter(name => !["validateReferenceCases", "referenceCases"].includes(name))
    .filter(name => typeof (api as Record<string, unknown>)[name] === "function")
    .map(name => vi.spyOn(api as unknown as Record<string, () => unknown>, name));
  render(<ReferenceCasesPanel project={project} context={context}/>);
  await open();
  fireEvent.click(screen.getByRole("checkbox", { name: "Show what happened next" })); await settle(); await settle();
  fireEvent.change(screen.getByRole("combobox", { name: "Alternative" }), { target: { value: "a" } }); await settle(); await settle();
  expect(route.mock.calls.at(-1)?.[3]).toBe("a");
  expect(route.mock.calls.every(call => call[0] === project)).toBe(true);
  for (const spy of others) expect(spy).not.toHaveBeenCalled();
  expect(canonical(project)).toBe(before);
});
