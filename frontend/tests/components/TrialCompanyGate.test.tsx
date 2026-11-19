import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import { CompanyExplorer } from "../../src/components/CompanyExplorer";
import { CompanyName, CompanyExplorationContext, companyRow, companySvg, useCompanyExploration } from "../../src/components/companyExploration";
import { ContributionsChart } from "../../src/components/results/ResultsCharts";
import { context, project, record } from "../results/fixture";
afterEach(() => vi.restoreAllMocks());

it("blocks company names, rows and SVG actions before any selection or drawer callback", () => {
  const open = vi.fn(), select = vi.fn(), exploration = { open, hint: vi.fn(), clearHint: vi.fn(), blocked: true };
  const view = render(<CompanyExplorationContext value={exploration}>
    <CompanyName id="a">Same</CompanyName><table><tbody><tr {...companyRow(exploration, "a", undefined, select)}><td>Row</td></tr></tbody></table>
    <svg><g {...companySvg(exploration, "a", "Same")}/></svg>
    <ContributionsChart record={record} view={{ sort: "rank", precision: "4", hidden_alternative_ids: [], hidden_criterion_ids: [] }} order={["a", "b", "c"]}
      selectedAlternative={null} selectedCriterion={null} onAlternative={select} onCriterion={select}/>
  </CompanyExplorationContext>);
  const name = screen.getByRole("button", { name: "Same" }); expect(name).toBeDisabled(); fireEvent.click(name);
  fireEvent.click(screen.getByText("Row", { exact: true }));
  const svg = view.container.querySelector('svg > g[aria-disabled="true"]'); if (!svg) throw Error("Blocked SVG missing"); fireEvent.keyDown(svg, { key: "Enter" });
  const segment = view.container.querySelector('rect[data-contribution]'); if (!segment) throw Error("Segment missing");
  fireEvent.click(segment); fireEvent.keyDown(segment, { key: " " });
  expect(open).not.toHaveBeenCalled(); expect(select).not.toHaveBeenCalled();
});
function DirectOpen() {
  const exploration = useCompanyExploration();
  return <button type="button" onClick={() => exploration?.open("a")}>Attempt programmatic detail</button>;
}
it("the drawer owner refuses an opening request during a trial without reading or changing the project", () => {
  const details = vi.spyOn(api, "screeningDetails"), edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"), before = structuredClone(project);
  render(<CompanyExplorer project={project} context={context} dossier={null} studyEvidence={null} onSensitivity={vi.fn()} blocked><DirectOpen/></CompanyExplorer>);
  fireEvent.click(screen.getByRole("button", { name: "Attempt programmatic detail" })); expect(screen.queryByRole("dialog")).toBeNull();
  expect(details).not.toHaveBeenCalled(); expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
});
