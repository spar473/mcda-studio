import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RankingChart, ContributionsChart, ScenarioComparisonChart } from "../../src/components/results/ResultsCharts";
import type { AnalysisPresentation, ScenarioComparison, ValueRecord } from "../../src/api/types";
import base from "../fixtures/svg-8efe702/base.json";
import sorting from "../fixtures/svg-8efe702/sorting.json";
import hidden from "../fixtures/svg-8efe702/selected-hidden.json";
import scenario from "../fixtures/svg-8efe702/scenario.json";
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useId: () => "_r_fixture_" }));
vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));

// Text nodes, element order, all attributes (including every numeric attribute), and
// metadata stay exact. Only React-generated id attribute VALUES are exempted.
function contents(xml: string): unknown {
  const doc = new DOMParser().parseFromString(xml, "image/svg+xml");
  expect(doc.querySelector("parsererror")).toBeNull();
  function visit(node: Node): unknown {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue;
    if (!(node instanceof Element)) return null;
    return { tag: node.tagName,
      attributes: [...node.attributes].map(a => [a.name, a.name === "id" && /^_r_/.test(a.value) ? "React ID" : a.value]).sort(),
      children: [...node.childNodes].map(visit) };
  }
  return visit(doc.documentElement);
}
describe("SVG export contents captured from 8efe702", () => {
  it.each([base, sorting, hidden])("preserves ranking and contributions, including classes, precision, selection and hidden series ($props.view.precision)", fixture => {
    const props = { ...fixture.props, record: fixture.props.record as ValueRecord, view: fixture.props.view as AnalysisPresentation,
      onAlternative: vi.fn(), onCriterion: vi.fn() };
    const view = render(<><RankingChart {...props}/><ContributionsChart {...props}/></>);
    expect(view.container.querySelectorAll("svg")).toHaveLength(2); // no hidden export duplicates
    const serializer = vi.spyOn(XMLSerializer.prototype, "serializeToString");
    for (const [i, kind] of ["ranking", "contributions"].entries()) {
      fireEvent.click(screen.getByRole("button", { name: `Download ${kind} SVG` }));
      expect(contents(serializer.mock.results.at(-1)?.value as string)).toEqual(contents(fixture.exports[i] ?? ""));
    }
    serializer.mockRestore();
    expect(view.container.querySelectorAll("svg")).toHaveLength(2);
  });
  it("preserves the original scenario export text, geometry and metadata", () => {
    const view = render(<ScenarioComparisonChart comparison={scenario.comparison as ScenarioComparison} alternatives={scenario.alternatives}
      projectId="p1" selectedAlternative="a" onAlternative={vi.fn()}/>);
    const serializer = vi.spyOn(XMLSerializer.prototype, "serializeToString");
    fireEvent.click(screen.getByRole("button", { name: "Download comparison SVG" }));
    expect(contents(serializer.mock.results.at(-1)?.value as string)).toEqual(contents(scenario.svg));
    serializer.mockRestore(); expect(view.container.querySelectorAll("svg")).toHaveLength(1);
  });
  it("rejects a drift in text, numeric attributes, or metadata", () => {
    const original = base.exports[0] ?? "";
    for (const drift of [original.replace('x="280"', 'x="281"'), original.replace('Overall MAVT values', 'Changed title'), original.replace('"record_digest"', '"other_digest"')]) {
      expect(drift).not.toBe(original); expect(contents(drift)).not.toEqual(contents(original));
    }
  });
});
