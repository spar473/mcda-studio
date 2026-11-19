import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { EvidenceDossier, ScreeningDetails } from "../../src/api/types";
import { CompanyExplorer } from "../../src/components/CompanyExplorer";
import { CompanyName } from "../../src/components/companyExploration";
import { RatingHint } from "../../src/components/RatingHint";
import { ContributionsChart, RankingChart } from "../../src/components/results/ResultsCharts";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { context, project as fixtureProject, record } from "../results/fixture";

const project = structuredClone(fixtureProject);
project.performances = [
  { alternative_id: "a", criterion_id: "cost", value: 8 },
  { alternative_id: "a", criterion_id: "quality", value: 6 },
];
const dossier: EvidenceDossier = { schema_version: 1, project_fingerprint: "fp", claims: [{
  id: "quote", alternative_id: "a", criterion_id: "cost", value: 8, unit: "kg",
  source: { name: "Quotation", reference: "https://example.invalid/quotation", location: "p2", date: "2026-10-31", description: "Judgement: Price per item", classification: "self_reported" },
  origin: { kind: "tool", proposed_by: "Analyst", tool_id: "extractor", tool_version: "1" },
  review: null, uncertainty_lower: null, uncertainty_upper: null, outdated: false,
}] };
function details(id = "a", ctx = context, value = .7): ScreeningDetails {
  return { project_fingerprint: ctx.fingerprint, configuration: ctx.configuration, weight_profile_id: ctx.resolvedProfileId, scenario_id: ctx.scenarioId,
    status: "available", reason: "", sensitivity: null, alternative: {
      row: { alternative_id: id, name: "Same", rank: 1, value, class_id: null, class_name: null, margin: null, nearest_boundary_class_id: null,
        requirements: null, drivers: [], open_questions: null, fragility: { status: "change", kind: "rank", criterion_id: "cost", criterion_name: "Cost", direction: "lower", base_local_weight: .5,
          local_weight: .1234567890123456, weight_change: .3765432109876544, other_alternative_id: "b", class_after_id: null, tied_with: [] } },
      header_facts: [], requirements: null, questions: [],
      contributions: [{ criterion_id: "cost", name: "Cost", contribution: .4 }, { criterion_id: "quality", name: "Quality", contribution: .3 }],
      ratings: [{ criterion_id: "cost", name: "Cost", measurement: 8, rubric_text: project.criteria.find(c => c.id === "cost")?.description ?? "", claim_ids: ["quote"] },
        { criterion_id: "quality", name: "Quality", measurement: 6, rubric_text: "", claim_ids: [] }],
    } };
}
const tick = async () => act(async () => { await vi.advanceTimersByTimeAsync(125); });
beforeEach(() => { vi.useFakeTimers(); vi.spyOn(api, "screeningDetails").mockResolvedValue(details()); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
function mounted(ctx = context, loaded: EvidenceDossier | null = dossier) {
  const onSensitivity = vi.fn(), loadEvidence = vi.fn();
  const props = { project, context: ctx, dossier: loaded, studyEvidence: { title: "Study", load: loadEvidence }, onSensitivity };
  const element = (next = props) => <CompanyExplorer {...next}><CompanyName id="a">Same</CompanyName></CompanyExplorer>;
  const view = render(element());
  const opener = screen.getByRole("button", { name: "Same" }); opener.focus(); fireEvent.click(opener);
  return { ...view, opener, onSensitivity, loadEvidence, element, props };
}

describe("read-only company exploration", () => {
  it("uses neutral words for any kind of alternative, in its text and its accessible names", async () => {
    mounted(); await tick();
    const dialog = screen.getByRole("dialog", { name: "Same" });
    const names = [...dialog.querySelectorAll("[aria-label]")].map(element => element.getAttribute("aria-label") ?? "");
    expect(names).toEqual(expect.arrayContaining(["Alternative requirements", "Alternative contributions", "Alternative closest change", "Alternative ratings and sources", "Alternative open questions"]));
    expect(within(dialog).getByRole("button", { name: "Close alternative detail" })).toBeVisible();
    for (const text of [dialog.textContent, ...names, ...[...document.querySelectorAll("[aria-label]")].map(element => element.getAttribute("aria-label") ?? "")]) {
      expect(text).not.toMatch(/compan|partner/i);
    }
  });
  it("joins every returned contribution, complete rubric and source date, traps links, and returns focus without editing", async () => {
    const before = structuredClone(project), originalDossier = structuredClone(dossier), edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject");
    const view = mounted(); await tick();
    const dialog = screen.getByRole("dialog", { name: "Same" });
    expect(view.container.querySelector(".company-exploration-content")).toHaveAttribute("inert");
    expect(within(dialog).getByText("0.7000", { exact: true })).toBeVisible();
    expect(within(dialog).getByRole("region", { name: "Alternative contributions" }).querySelectorAll("li")).toHaveLength(2);
    const ratings = within(dialog).getByRole("region", { name: "Alternative ratings and sources" });
    fireEvent.click(within(ratings).getByText("Cost · 8", { exact: true }));
    expect(ratings).toHaveTextContent(project.criteria.find(c => c.id === "cost")?.description ?? "missing rubric");
    expect(ratings).toHaveTextContent("2026-10-31"); expect(ratings).toHaveTextContent("Judgement");
    fireEvent.click(within(ratings).getByText("Quality · 6", { exact: true }));
    expect(within(ratings).getByText("No rubric text stated.", { exact: true })).toBeVisible();
    const link = within(ratings).getByRole("link", { name: "Quotation" }); expect(link).toHaveAttribute("href", dossier.claims[0]?.source.reference);
    link.focus(); expect(link).toHaveFocus();
    const close = within(dialog).getByRole("button", { name: "Close alternative detail" });
    close.focus(); fireEvent.keyDown(close, { key: "Tab" }); expect(within(dialog).getAllByRole("button")[0]).toHaveFocus();
    fireEvent.keyDown(document.activeElement ?? dialog, { key: "Tab", shiftKey: true }); expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: "Escape" }); expect(screen.queryByRole("dialog")).toBeNull(); expect(view.opener).toHaveFocus();
    expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before); expect(dossier).toEqual(originalDossier);
  });
  it("keeps Escape and the focus trap working if loading removes the focused control, and provides an explicit close icon", async () => {
    const view = mounted(context, null); await tick();
    screen.getByRole("button", { name: "Load the study's evidence" }).focus();
    view.rerender(view.element({ ...view.props, dossier }));
    fireEvent.keyDown(document.body, { key: "Tab" });
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
    await tick(); screen.getByRole("button", { name: "Show in Sensitivity" }).focus();
    view.rerender(view.element({ ...view.props, dossier: null }));
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull(); expect(view.opener).toHaveFocus();
    view.rerender(view.element()); fireEvent.click(view.opener); await tick();
    fireEvent.click(screen.getByRole("button", { name: "Close alternative drawer" }));
    expect(screen.queryByRole("dialog")).toBeNull(); expect(view.opener).toHaveFocus();
  });
  it("offers the shared evidence loader without inventing sources or review state", async () => {
    const response = details();
    if (!response.alternative) throw Error("fixture detail");
    response.alternative.ratings = response.alternative.ratings.map(r => ({ ...r, claim_ids: [] }));
    vi.mocked(api.screeningDetails).mockResolvedValue(response);
    const view = mounted(context, null); await tick();
    fireEvent.click(screen.getByRole("button", { name: "Load the study's evidence" })); expect(view.loadEvidence).toHaveBeenCalledOnce();
    expect(screen.queryByRole("link", { name: "Quotation" })).toBeNull(); expect(screen.queryByText("accepted", { exact: true })).toBeNull();
  });
  it("sends the exact backend crossover weight and its viewed profile to Sensitivity", async () => {
    const view = mounted(); await tick(); fireEvent.click(screen.getByRole("button", { name: "Show in Sensitivity" }));
    expect(view.onSensitivity).toHaveBeenCalledWith({ criterionId: "cost", weight: .1234567890123456, context });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it.each(["success", "error"])("discards a late prior-profile %s", async outcome => {
    let complete: (value: ScreeningDetails) => void = () => undefined, fail: (error: Error) => void = () => undefined;
    vi.mocked(api.screeningDetails).mockImplementationOnce(() => new Promise((resolve, reject) => { complete = resolve; fail = reject; }));
    const view = mounted(); await tick();
    const next = resolveContext(project, "fp", { ...BASE_SELECTION, profileId: "second" });
    vi.mocked(api.screeningDetails).mockResolvedValue(details("a", next, .66));
    view.rerender(view.element({ ...view.props, context: next })); await tick();
    expect(screen.getByRole("dialog")).toHaveTextContent("Second profile"); expect(screen.getByText("0.6600", { exact: true })).toBeVisible();
    await act(async () => { if (outcome === "success") complete(details()); else fail(Error("Obsolete detail error")); await Promise.resolve(); });
    expect(screen.queryByText("0.7000", { exact: true })).toBeNull(); expect(screen.queryByRole("alert")).toBeNull();
  });
  it("hides a completed old result as soon as the context changes and closes for a deleted company", async () => {
    const view = mounted(); await tick(); expect(screen.getByText("0.7000", { exact: true })).toBeVisible();
    const next = resolveContext(project, "next", BASE_SELECTION);
    view.rerender(view.element({ ...view.props, context: next }));
    expect(screen.queryByText("0.7000", { exact: true })).toBeNull(); expect(screen.getByText("Loading alternative detail…")).toBeVisible();
    const changed = { ...project, alternatives: project.alternatives.filter(a => a.id !== "a") };
    view.rerender(view.element({ ...view.props, project: changed, context: next })); expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("refuses a wrong-company response", async () => {
    vi.mocked(api.screeningDetails).mockResolvedValue(details("b")); mounted(); await tick();
    expect(screen.getByRole("alert")).toHaveTextContent("does not match"); expect(screen.queryByText("All scored contributions")).toBeNull();
  });
  it.each(["Enter", " "])("opens the same company from ranking-key activation %s", async key => {
    const selected = vi.fn(), before = structuredClone(project);
    render(<CompanyExplorer project={project} context={context} dossier={null} studyEvidence={null} onSensitivity={vi.fn()}>
      <RankingChart record={record} view={{ sort: "rank", precision: "4", hidden_alternative_ids: [], hidden_criterion_ids: [] }} order={["a", "b", "c"]}
        selectedAlternative={null} selectedCriterion={null} onAlternative={selected} onCriterion={vi.fn()}/>
    </CompanyExplorer>);
    fireEvent.keyDown(screen.getByRole("button", { name: "Inspect alternative Same (a), rank 1, value 0.7" }), { key });
    await tick(); expect(screen.getByRole("dialog", { name: "Same" })).toHaveTextContent("All scored contributions");
    expect(selected).toHaveBeenCalledWith("a"); expect(project).toEqual(before);
  });
});

it("shows the same criterion, backend contribution and complete rubric from real chart hover and focus", async () => {
  const before = structuredClone(project), onAlternative = vi.fn(), onCriterion = vi.fn();
  render(<CompanyExplorer project={project} context={context} dossier={null} studyEvidence={null} onSensitivity={vi.fn()}>
    <ContributionsChart record={record} view={{ sort: "rank", precision: "4", hidden_alternative_ids: [], hidden_criterion_ids: [] }} order={["a", "b", "c"]}
      selectedAlternative={null} selectedCriterion={null} onAlternative={onAlternative} onCriterion={onCriterion}/>
  </CompanyExplorer>);
  const trigger = screen.getByRole("button", { name: "Inspect contribution Cost (cost) for Same: 0.4" });
  const expected = `Cost · contribution 0.4000. ${record.criteria[0]?.description ?? ""}`;
  fireEvent.mouseEnter(trigger); expect(screen.getByRole("tooltip")).toHaveTextContent(expected);
  fireEvent.mouseLeave(trigger); expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => trigger.focus()); expect(screen.getByRole("tooltip")).toHaveTextContent(expected);
  fireEvent.mouseLeave(trigger); expect(screen.getByRole("tooltip")).toHaveTextContent(expected);
  fireEvent.keyDown(trigger, { key: "Enter" }); await tick();
  expect(screen.getByRole("dialog", { name: "Same" })).toHaveTextContent("All scored contributions");
  expect(onAlternative).toHaveBeenCalledWith("a"); expect(onCriterion).toHaveBeenCalledWith("cost"); expect(project).toEqual(before);
});
it("states when no rubric exists, with hover and keyboard parity inside the drawer primitive", () => {
  render(<RatingHint text="Quality: 0.3000. No rubric text stated.">Quality</RatingHint>);
  const trigger = screen.getByText("Quality", { exact: true }); fireEvent.mouseEnter(trigger);
  expect(screen.getByRole("tooltip")).toHaveTextContent("No rubric text stated."); fireEvent.mouseLeave(trigger); expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => trigger.focus()); expect(screen.getByRole("tooltip")).toHaveTextContent("No rubric text stated.");
  fireEvent.keyDown(trigger, { key: "Escape" }); expect(screen.queryByRole("tooltip")).toBeNull();
});
