import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnalysisRecord } from "../../src/api/types";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import * as downloads from "../../src/components/results/downloads";
import { context, project, record } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const valid = { issues: [] };
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
function setup() { return render(<ResultsPanel project={project} context={context} validation={valid}/>); }
beforeEach(() => { vi.useFakeTimers(); vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(record)); });
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers(); });

describe("authoritative linked results", () => {
  it("renders competition ranks, all contribution segments and mixed-unit partial values by stable ID", async () => {
    setup(); await settle();
    const rows = within(screen.getByRole("table", { name: "Ranking" })).getAllByRole("row");
    expect(rows.slice(1).map(row => within(row).getAllByRole("cell")[0]?.textContent)).toEqual(["1", "1", "3"]);
    const svg = screen.getByRole("group", { name: "Overall MAVT values" });
    expect([...svg.querySelectorAll("text")].map(node => node.textContent).filter(text => text.includes("· rank"))).toEqual(["0.7000 · rank 1", "0.7000 · rank 1", "0.2000 · rank 3"]);
    const contributions = screen.getByRole("group", { name: "Weighted leaf contributions" });
    expect(contributions.querySelectorAll("rect[data-contribution]")).toHaveLength(6);
    expect(within(contributions).getByRole("list", { name: "Leaf criterion legend" })).toHaveTextContent("Cost (cost)");
    expect(contributions.querySelector('[data-alternative-id="b"] [data-criterion-id="cost"]')).toHaveAttribute("data-contribution", "0.3");
    expect(screen.getByRole("table", { name: "Partial-value heatmap" })).toHaveTextContent("Raw: 8 kg");
    expect(screen.getByRole("table", { name: "Partial-value heatmap" })).toHaveTextContent("Raw: 8 %");
  });
  it("selecting heatmap and chart elements links alternative, criterion and hierarchy without reevaluation or edits", async () => {
    const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"); const before = structuredClone(project);
    setup(); await settle();
    fireEvent.click(screen.getByRole("button", { name: "Inspect Same, Cost: preference 0.6, raw 6 kg" }));
    expect(screen.getByLabelText("Alternative to inspect")).toHaveValue("b");
    expect(screen.getByLabelText("Criterion to inspect")).toHaveValue("cost");
    expect(screen.getByRole("region", { name: "Selected criterion and alternative" })).toHaveTextContent("G / Cost");
    expect(screen.getByRole("region", { name: "Selected criterion and alternative" })).toHaveTextContent("g: 1 → cost: 0.5");
    const bar = screen.getByRole("button", { name: "Inspect alternative Same (a), rank 1, value 0.7" });
    fireEvent.keyDown(bar, { key: "Enter" }); expect(screen.getByLabelText("Alternative to inspect")).toHaveValue("a");
    await settle(); expect(api.analysisRecord).toHaveBeenCalledTimes(1); expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
  });
  it("Retry re-requests the same completed record after a failure, without edits or saves", async () => {
    vi.mocked(api.analysisRecord).mockRejectedValueOnce(new Error("Connection lost"));
    const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"); const before = structuredClone(project);
    setup(); await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("Connection lost");
    fireEvent.click(screen.getByRole("button", { name: "Retry analysis" }));
    expect(screen.getByText("Calculating completed analysis…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    await settle(); expect(screen.getByRole("table", { name: "Ranking" })).toBeVisible();
    const calls = vi.mocked(api.analysisRecord).mock.calls;
    expect(calls).toHaveLength(2); expect(calls[1]?.[0]).toBe(calls[0]?.[0]); expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);
    expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
  });
  it("heatmap and dominance cells support keyboard arrow navigation", async () => {
    setup(); await settle();
    const first = screen.getByRole("button", { name: "Inspect Same, Cost: preference 0.8, raw 8 kg" });
    first.focus(); fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "Inspect Same, Quality: preference 0.6, raw 6 %" })).toHaveFocus();
    const matrix = screen.getByRole("table", { name: "Dominance matrix" });
    const cell = matrix.querySelector<HTMLButtonElement>('[data-grid-row="0"][data-grid-column="0"]');
    if (!cell) throw Error("missing keyboard cell"); cell.focus(); fireEvent.keyDown(cell, { key: "ArrowRight" });
    expect(matrix.querySelector('[data-grid-row="0"][data-grid-column="1"]')).toHaveFocus();
  });
  it("hidden leaves are labelled gaps, never renormalised totals; tables stay complete", async () => {
    setup(); await settle(); fireEvent.click(screen.getByText("Chart visibility and accessible criterion legend"));
    fireEvent.click(screen.getByLabelText("Show criterion Cost")); fireEvent.click(screen.getByLabelText(`Show alternative ${project.alternatives[0]?.name ?? "C"}`));
    expect(screen.getByLabelText("Chart visibility summary")).toHaveTextContent("Hidden criterion segments: cost");
    expect(screen.getByTestId("contribution-total-a")).toHaveTextContent("0.7000");
    const chart = screen.getByRole("group", { name: "Weighted leaf contributions" });
    expect(chart.querySelector('[data-alternative-id="a"] [data-criterion-id="cost"]')).toHaveAttribute("data-hidden", "true");
    expect(chart.querySelector('[data-alternative-id="a"] [data-criterion-id="quality"]')).toHaveAttribute("width", "195");
    expect(chart.querySelector('[data-alternative-id="c"]')).toBeNull();
    expect([...chart.querySelectorAll("text")].map(node => node.textContent).filter(text => text.includes("· rank"))).toEqual(["0.7000 · rank 1", "0.7000 · rank 1"]);
    expect(within(screen.getByRole("table", { name: "Contributions" })).getAllByRole("row")).toHaveLength(5);
    expect(within(screen.getByRole("table", { name: "Ranking" })).getAllByRole("row")).toHaveLength(4);
  });
  it("sort and full precision are presentation state, and preserve competition rank/IDs", async () => {
    setup(); await settle(); fireEvent.change(screen.getByLabelText("Results order"), { target: { value: "project" } });
    fireEvent.change(screen.getByLabelText("Results precision"), { target: { value: "full" } });
    const rows = within(screen.getByRole("table", { name: "Ranking" })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("c"); expect(rows[1]).toHaveTextContent("3"); expect(rows[1]).toHaveTextContent("0.2");
    expect(api.analysisRecord).toHaveBeenCalledTimes(1);
  });
  it("dominance matrix and pair inspection use engine relationships, not overall rank", async () => {
    setup(); await settle();
    const matrix = screen.getByRole("table", { name: "Dominance matrix" });
    const pair = within(matrix).getAllByRole("button", { name: `Same versus ${project.alternatives[0]?.name ?? "C"}: Dominates` })[0];
    if (!pair) throw Error("missing pair"); fireEvent.click(pair);
    expect(screen.getByRole("table", { name: "Dominance supporting partial values" })).toHaveTextContent("0.8000");
    expect(screen.getByRole("table", { name: "Dominance supporting partial values" })).toHaveTextContent("0.2000");
    expect(screen.getByLabelText("Alternative to inspect")).toHaveValue("a");
    expect(within(matrix).getAllByRole("button", { name: "Same versus Same: Incomparable" })).toHaveLength(2);
  });
  it("SVG downloads include revision, common axis and explicit hidden-series metadata with no scripts", async () => {
    const changed = structuredClone(record); const alt = changed.result.alternatives[0]; if (alt) alt.name = '<script>alert("x")</script>';
    vi.mocked(api.analysisRecord).mockResolvedValue(changed); const serializer = vi.spyOn(XMLSerializer.prototype, "serializeToString");
    setup(); await settle(); fireEvent.click(screen.getByText("Chart visibility and accessible criterion legend")); fireEvent.click(screen.getByLabelText("Show criterion Cost"));
    fireEvent.click(screen.getByRole("button", { name: "Download contributions SVG" }));
    expect(downloads.saveDownload).toHaveBeenCalledTimes(1);
    const xml = serializer.mock.results[0]?.value as string; const document = new DOMParser().parseFromString(xml, "image/svg+xml");
    expect(document.querySelector("parsererror")).toBeNull(); expect(document.querySelector("script")).toBeNull();
    expect(document.documentElement.textContent).toContain("Hidden criteria: cost");
    expect(document.documentElement.textContent).toContain("preference value");
    const metadata = JSON.parse(document.querySelector("metadata")?.textContent ?? "{}") as { presentation: { hidden_criterion_ids: string[] } };
    expect(metadata.presentation.hidden_criterion_ids).toEqual(["cost"]);
  });
  it("JSON/CSV download actions capture the completed record and current visibility", async () => {
    vi.spyOn(api, "exportAnalysis").mockResolvedValue({ blob: new Blob(["data"]), filename: "analysis.json" });
    setup(); await settle();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Download analysis JSON" })); await Promise.resolve(); });
    expect(api.exportAnalysis).toHaveBeenCalledWith(expect.objectContaining({ project, expected_project_fingerprint: "fp", expected_record_digest: record.record_digest, format: "json" }), expect.any(AbortSignal));
    expect(downloads.saveDownload).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("CSV table"), { target: { value: "partial_values" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Download CSV" })); await Promise.resolve(); });
    expect(api.exportAnalysis).toHaveBeenLastCalledWith(expect.objectContaining({ table: "partial_values", format: "csv" }), expect.any(AbortSignal));
  });
  it("a late download is aborted and suppressed after the model context changes", async () => {
    let release!: (file: { blob: Blob; filename: string }) => void;
    vi.spyOn(api, "exportAnalysis").mockReturnValue(new Promise(resolve => { release = resolve; }));
    const view = setup(); await settle(); fireEvent.click(screen.getByRole("button", { name: "Download analysis JSON" }));
    const fresh = structuredClone(record); fresh.result.project_fingerprint = "fresh"; fresh.record_digest = "b".repeat(64);
    vi.mocked(api.analysisRecord).mockResolvedValue(fresh); view.rerender(<ResultsPanel project={project} context={{ ...context, fingerprint: "fresh" }} validation={valid}/>); await settle();
    await act(async () => { release({ blob: new Blob(["old"]), filename: "old.json" }); await Promise.resolve(); });
    expect(vi.mocked(api.exportAnalysis).mock.calls[0]?.[1]?.aborted).toBe(true); expect(downloads.saveDownload).not.toHaveBeenCalled();
  });
  it("pending, invalid and failed analyses cannot expose exports or old charts", async () => {
    vi.mocked(api.analysisRecord).mockReturnValue(new Promise(() => undefined)); const view = setup(); await settle();
    expect(screen.queryByRole("table", { name: "Ranking" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Download analysis JSON" })).not.toBeInTheDocument();
    view.rerender(<ResultsPanel project={project} context={context} validation={{ issues: [{ code: "MISSING", severity: "error", message: "missing", path: "" }] }}/>);
    expect(screen.getByRole("status")).toHaveTextContent("validation error");
  });
  it.each(["revision", "profile", "scenario", "identifiers"])("rejects incorrect %s record provenance", async field => {
    const bad = structuredClone(record);
    if (field === "revision") bad.result.project_fingerprint = "wrong";
    if (field === "profile") bad.result.weight_profile_id = "wrong";
    if (field === "scenario") bad.result.scenario_id = "wrong";
    if (field === "identifiers") bad.alternative_order = ["unknown"];
    vi.mocked(api.analysisRecord).mockResolvedValue(bad); setup(); await settle();
    expect(screen.getByRole("alert")).toHaveTextContent(/does not match|do not match/); expect(screen.queryByRole("table", { name: "Ranking" })).not.toBeInTheDocument();
  });
  it("incomplete detail maps cannot silently become fabricated zero contributions", async () => {
    const bad = structuredClone(record); if (bad.result.alternatives[0]) delete bad.result.alternatives[0].weighted_contributions.cost;
    vi.mocked(api.analysisRecord).mockResolvedValue(bad); setup(); await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("does not match"); expect(screen.queryByRole("table", { name: "Contributions" })).not.toBeInTheDocument();
  });
  it("deleted alternative selections clear safely and stable IDs retain renamed labels", async () => {
    const view = setup(); await settle(); fireEvent.change(screen.getByLabelText("Alternative to inspect"), { target: { value: "c" } });
    const freshProject = structuredClone(project); freshProject.alternatives = freshProject.alternatives.filter(a => a.id !== "c");
    const named = freshProject.alternatives.find(a => a.id === "a"); if (named) named.name = "Renamed alternative";
    const fresh = structuredClone(record); fresh.record_digest = "b".repeat(64); fresh.result.project_fingerprint = "fresh";
    fresh.alternative_order = fresh.alternative_order.filter(id => id !== "c");
    fresh.result.alternatives = fresh.result.alternatives.filter(a => a.alternative_id !== "c"); fresh.result.ranking = fresh.result.ranking.filter(a => a.alternative_id !== "c");
    for (const alt of [...fresh.result.alternatives, ...fresh.result.ranking]) if (alt.alternative_id === "a") alt.name = "Renamed alternative";
    delete fresh.dominance_relations.c; for (const row of Object.values(fresh.dominance_relations)) delete row.c;
    delete fresh.contribution_totals.c; fresh.result.dominance = [];
    vi.mocked(api.analysisRecord).mockResolvedValue(fresh);
    view.rerender(<ResultsPanel project={freshProject} context={{ ...context, fingerprint: "fresh" }} validation={valid}/>); await settle();
    expect(screen.getByLabelText("Alternative to inspect")).toHaveValue("");
    expect(screen.getByRole("table", { name: "Ranking" })).toHaveTextContent("Renamed alternative");
  });
  it("a previously completed record disappears immediately while a new context is still pending", async () => {
    const view = setup(); await settle(); expect(screen.getByRole("table", { name: "Ranking" })).toBeVisible();
    vi.mocked(api.analysisRecord).mockReturnValue(new Promise(() => undefined));
    view.rerender(<ResultsPanel project={project} context={{ ...context, fingerprint: "fresh" }} validation={valid}/>);
    expect(screen.queryByRole("table", { name: "Ranking" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download analysis JSON" })).not.toBeInTheDocument();
    await settle(); expect(screen.getByRole("status")).toHaveTextContent("Calculating");
  });
  it("context switches hide old output immediately and reject an obsolete completion", async () => {
    let release!: (value: AnalysisRecord) => void;
    vi.mocked(api.analysisRecord).mockReturnValueOnce(new Promise(resolve => { release = resolve; }));
    const view = setup(); await settle(); const fresh = structuredClone(record); fresh.result.project_fingerprint = "fresh"; fresh.record_digest = "b".repeat(64);
    vi.mocked(api.analysisRecord).mockResolvedValue(fresh); view.rerender(<ResultsPanel project={project} context={{ ...context, fingerprint: "fresh" }} validation={valid}/>);
    expect(screen.queryByRole("table", { name: "Ranking" })).not.toBeInTheDocument(); await settle();
    await act(async () => { release(record); await Promise.resolve(); });
    expect(screen.getByLabelText("Results analysis context")).toHaveTextContent("fresh");
    expect(api.analysisRecord).toHaveBeenCalledTimes(2);
  });
});
