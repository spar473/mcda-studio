import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ProfileComparison, Project, ScreeningSummary } from "../../src/api/types";
import { CompanyExplorationContext } from "../../src/components/companyExploration";
import { PartnerComparison } from "../../src/components/results/PartnerComparison";
import { BASE_SELECTION, resolveContext, type AnalysisContext } from "../../src/state/analysisContext";
import { context, project, record } from "../results/fixture";
import studyJSON from "../fixtures/screening-study-project.json";

// Presentation fixtures retain the backend's tied competition ranks. Actual
// numerical summaries/movements are checked independently in the Python suite.
function response(ctx: AnalysisContext = context, ids: [string, string] = ["first", "second"], source: Project = project): ProfileComparison {
  const summary = (id: string): ScreeningSummary => ({
    project_fingerprint: ctx.fingerprint, configuration: { ...ctx.configuration, weight_profile_id: id }, weight_profile_id: id,
    scenario_id: ctx.scenarioId, status: "available", reason: "", issue_codes: [], label: "Screening preferences", fragility_definition: "One weight at a time",
    rows: record.result.ranking.map(row => ({ ...row, class_id: null, class_name: null, margin: null, nearest_boundary_class_id: null,
      requirements: null, drivers: [], fragility: null, open_questions: null })),
    columns: [], project_open_questions: null, excluded_criteria: [], limitations: [],
  });
  return { project_fingerprint: ctx.fingerprint, configuration: ctx.configuration, scenario_id: ctx.scenarioId,
    profiles: ids.map(id => ({ profile_id: id, name: source.weight_profiles.find(profile => profile.id === id)?.name ?? id, summary: summary(id) })),
    movements: [
      { alternative_id: "a", from_profile_id: ids[0], to_profile_id: ids[1], from_rank: 1, to_rank: 1, places_changed: 0, emphasize: false, line_class_id: null },
      { alternative_id: "b", from_profile_id: ids[0], to_profile_id: ids[1], from_rank: 1, to_rank: 1, places_changed: 0, emphasize: false, line_class_id: null },
      { alternative_id: "c", from_profile_id: ids[0], to_profile_id: ids[1], from_rank: 3, to_rank: 3, places_changed: 0, emphasize: false, line_class_id: null },
    ],
  };
}
const tick = async () => act(async () => { await vi.advanceTimersByTimeAsync(125); });
beforeEach(() => {
  vi.useFakeTimers(); vi.spyOn(api, "screeningProfiles").mockImplementation((source, cfg, ids) => {
    const [left, right] = ids; if (!left || !right) throw Error("Two fixture profiles required");
    return Promise.resolve(response({ ...context, configuration: cfg }, [left, right], source));
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
const table = () => screen.getByRole("table", { name: "Profile rankings and movements" });

it("keeps the separate tied engine ranks and geometry, opens the right profile on keyboard, and never edits", async () => {
  const before = structuredClone(project), opening = structuredClone(context), open = vi.fn(), edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject");
  const view = render(<CompanyExplorationContext value={{ open, hint: vi.fn(), clearHint: vi.fn() }}>
    <PartnerComparison project={project} context={context} dossier={null}/>
  </CompanyExplorationContext>); await tick();
  expect(api.screeningProfiles).toHaveBeenCalledWith(project, context.configuration, ["first", "second"], expect.any(AbortSignal), undefined);
  expect(within(table()).getAllByRole("row").slice(1).map(row => within(row).getByRole("rowheader").textContent)).toEqual(record.result.ranking.map(row => row.name));
  const svg = screen.getByRole("group", { name: "Rankings by weight profile" });
  for (const id of ["a", "b"]) expect(svg.querySelector(`g[data-company-id="${id}"] > path`)).toHaveAttribute("d", "M 286 52 L 614 52");
  expect(svg.querySelector('g[data-company-id="c"] > path')).toHaveAttribute("d", "M 286 136 L 614 136");
  const right = svg.querySelector('g[data-company-id="a"] > g[role="button"]:last-child'); if (!right) throw Error("Right endpoint missing");
  fireEvent.keyDown(right, { key: " " }); expect(open).toHaveBeenLastCalledWith("a", "second");
  fireEvent.click(view.container.querySelector('g[data-company-id="a"] > path') ?? svg); expect(open).toHaveBeenLastCalledWith("a", "first");
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before); expect(context).toEqual(opening);
});

it("uses the backend mover flag rather than inferring it from display positions", async () => {
  const data = response(); if (!data.movements[0]) throw Error("Movement fixture missing");
  data.movements[0].emphasize = true; vi.mocked(api.screeningProfiles).mockResolvedValue(data);
  const view = render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  expect(view.container.querySelector('g[data-company-id="a"] > path')).toHaveAttribute("stroke-width", "4");
  expect(view.container.querySelector('g[data-company-id="b"] > path')).toHaveAttribute("stroke-width", "1.5");
});

it("swaps the ordered pair, immediately hides the old reading, and keeps source data unchanged", async () => {
  const before = structuredClone(project); render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  fireEvent.click(screen.getByRole("button", { name: "Swap profiles" })); expect(screen.queryByRole("table", { name: "Profile rankings and movements" })).toBeNull();
  await tick(); expect(screen.getByLabelText("Left profile")).toHaveValue("second"); expect(screen.getByLabelText("Right profile")).toHaveValue("first");
  expect(api.screeningProfiles).toHaveBeenLastCalledWith(project, context.configuration, ["second", "first"], expect.any(AbortSignal), undefined);
  expect(project).toEqual(before);
});

it.each(["success", "error"])("drops a late response for the previous ordered pair (%s)", async outcome => {
  let complete: (value: ProfileComparison) => void = () => undefined, fail: (error: Error) => void = () => undefined;
  vi.mocked(api.screeningProfiles).mockImplementationOnce(() => new Promise((resolve, reject) => { complete = resolve; fail = reject; }));
  render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  fireEvent.click(screen.getByRole("button", { name: "Swap profiles" })); await tick();
  expect(within(table()).getAllByRole("columnheader")[1]).toHaveTextContent("Second profile");
  await act(async () => { if (outcome === "success") complete(response()); else fail(Error("Old pair failure")); await Promise.resolve(); });
  expect(within(table()).getAllByRole("columnheader")[1]).toHaveTextContent("Second profile"); expect(screen.queryByRole("alert")).toBeNull();
});

it.each(["success", "error"])("drops a late source revision response (%s)", async outcome => {
  let complete: (value: ProfileComparison) => void = () => undefined, fail: (error: Error) => void = () => undefined;
  vi.mocked(api.screeningProfiles).mockImplementationOnce(() => new Promise((resolve, reject) => { complete = resolve; fail = reject; }));
  const view = render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  const next = resolveContext(project, "new-revision", BASE_SELECTION); vi.mocked(api.screeningProfiles).mockResolvedValue(response(next));
  view.rerender(<PartnerComparison project={project} context={next} dossier={null}/>); await tick(); expect(table()).toBeVisible();
  await act(async () => { if (outcome === "success") complete(response()); else fail(Error("Old revision failure")); await Promise.resolve(); });
  expect(table()).toBeVisible(); expect(screen.queryByRole("alert")).toBeNull();
});

it("refuses mismatched nested provenance and quietly explains a one-profile project", async () => {
  const wrong = response(); if (!wrong.profiles[1]) throw Error("Second profile missing"); wrong.profiles[1].summary.weight_profile_id = "first";
  vi.mocked(api.screeningProfiles).mockResolvedValue(wrong);
  const view = render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match"); expect(screen.queryByRole("table")).toBeNull();
  view.unmount(); vi.mocked(api.screeningProfiles).mockClear();
  render(<PartnerComparison project={{ ...project, weight_profiles: project.weight_profiles.slice(0, 1) }} context={context} dossier={null}/>); await tick();
  expect(screen.getByRole("status")).toHaveTextContent("Two weight profiles are needed"); expect(api.screeningProfiles).not.toHaveBeenCalled();
});

it.each(["success", "error"])("drops a late previous-scenario response (%s)", async outcome => {
  let complete: (value: ProfileComparison) => void = () => undefined, fail: (error: Error) => void = () => undefined;
  vi.mocked(api.screeningProfiles).mockImplementationOnce(() => new Promise((resolve, reject) => { complete = resolve; fail = reject; }));
  const source = { ...project, scenarios: [{ id: "alternate", name: "Alternate", weight_profile_id: "second", value_function_overrides: {} }] };
  const view = render(<PartnerComparison project={source} context={context} dossier={null}/>); await tick();
  const next = resolveContext(source, "fp", { ...BASE_SELECTION, scenarioId: "alternate" });
  vi.mocked(api.screeningProfiles).mockResolvedValue(response(next));
  view.rerender(<PartnerComparison project={source} context={next} dossier={null}/>); await tick(); expect(table()).toBeVisible();
  await act(async () => { if (outcome === "success") complete(response()); else fail(Error("Old scenario failure")); await Promise.resolve(); });
  expect(table()).toBeVisible(); expect(screen.queryByRole("alert")).toBeNull();
});

it("can choose any two of several profiles and reconciles a deleted selector without an old result", async () => {
  const first = project.weight_profiles[0]; if (!first) throw Error("Fixture profile missing");
  const source = { ...project, weight_profiles: [...project.weight_profiles, { ...first, id: "third", name: "Third partner" }] };
  let fingerprint = "fp";
  vi.mocked(api.screeningProfiles).mockImplementation((model, cfg, ids) => {
    const [left, right] = ids; if (!left || !right) throw Error("Two profiles required");
    return Promise.resolve(response({ ...context, fingerprint, configuration: cfg }, [left, right], model));
  });
  const before = structuredClone(source), view = render(<PartnerComparison project={source} context={context} dossier={null}/>); await tick();
  fireEvent.change(screen.getByLabelText("Right profile"), { target: { value: "third" } }); await tick();
  expect(within(table()).getAllByRole("columnheader")[2]).toHaveTextContent("Third partner");
  expect(api.screeningProfiles).toHaveBeenLastCalledWith(source, context.configuration, ["first", "third"], expect.any(AbortSignal), undefined);
  expect(source).toEqual(before);
  const changed = { ...source, weight_profiles: source.weight_profiles.filter(profile => profile.id !== "third") };
  fingerprint = "deleted-profile"; const next = resolveContext(changed, fingerprint, BASE_SELECTION);
  view.rerender(<PartnerComparison project={changed} context={next} dossier={null}/>);
  expect(screen.queryByRole("table", { name: "Profile rankings and movements" })).toBeNull(); await tick();
  expect(screen.getByLabelText("Right profile")).toHaveValue("second"); expect(table()).toBeVisible();
});

it("colours the connecting line by the left class and each dot by its own supplied class", async () => {
  const source = structuredClone(project), study = studyJSON as unknown as Project;
  if (!study.sorting) throw Error("Study sorting fixture missing"); source.sorting = structuredClone(study.sorting);
  const first = source.sorting.classes[0], second = source.sorting.classes[1]; if (!first || !second) throw Error("Two classes required");
  const data = response(context, ["first", "second"], source), left = data.profiles[0]?.summary.rows[0], right = data.profiles[1]?.summary.rows[0], movement = data.movements[0];
  if (!left || !right || !movement) throw Error("Endpoint fixture missing");
  left.class_id = first.id; left.class_name = first.name; right.class_id = second.id; right.class_name = second.name; movement.line_class_id = first.id;
  vi.mocked(api.screeningProfiles).mockResolvedValue(data);
  const view = render(<PartnerComparison project={source} context={context} dossier={null}/>); await tick();
  const path = view.container.querySelector('g[data-company-id="a"] > path'), dots = view.container.querySelectorAll('g[data-company-id="a"] circle');
  if (!path) throw Error("Connector missing"); expect(dots).toHaveLength(2);
  expect(dots[0]).toHaveAttribute("fill", path.getAttribute("stroke"));
  expect(dots[1]?.getAttribute("fill")).not.toBe(path.getAttribute("stroke"));
});

it.each(["rows", "movements"])("refuses a partial %s response rather than silently dropping a company", async kind => {
  const data = response();
  if (kind === "rows") data.profiles[0]?.summary.rows.pop(); else data.movements.pop();
  vi.mocked(api.screeningProfiles).mockResolvedValue(data);
  render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  expect(screen.getByRole("alert")).toHaveTextContent("alternatives do not match"); expect(screen.queryByRole("table")).toBeNull();
});

it("uses neutral words for any two weight profiles, in its text and its accessible names", async () => {
  render(<PartnerComparison project={project} context={context} dossier={null}/>); await tick();
  const region = screen.getByRole("region", { name: "Profile comparison" });
  expect(within(region).getByRole("heading", { name: "Compare profiles" })).toBeVisible();
  const names = [...region.querySelectorAll("[aria-label]")].map(element => element.getAttribute("aria-label") ?? "");
  expect(names).toEqual(expect.arrayContaining(["Rankings by weight profile", "Profile rankings and movements"]));
  for (const text of [region.textContent, ...names]) expect(text).not.toMatch(/compan|partner/i);
  expect(within(table()).getAllByRole("columnheader")[0]).toHaveTextContent("Alternative");
});
