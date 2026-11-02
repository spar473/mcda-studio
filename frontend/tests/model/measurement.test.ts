import { describe, expect, it } from "vitest";
import type { Operation } from "../../src/api/types";
import {
  hasMeasurements,
  opsAddLabel,
  opsChangeScaleType,
  opsMoveLabel,
  opsPatchScale,
  opsRemoveLabel,
  opsRenameLabel,
  opsSetKind,
  opsSetLabelValue,
} from "../../src/model/measurement";
import { META, node, ordinalScale, projectWith, ratioScale } from "../fixtures";

const grade = node("grade", null, 0, {
  scale: ordinalScale,
  value_function: { kind: "qualitative", mapping: { Low: 0, Mid: 0.5, High: 1 } },
});
const project = projectWith([grade], {
  performances: [
    { alternative_id: "a1", criterion_id: "grade", value: "Mid" },
    { alternative_id: "a2", criterion_id: "grade", value: "High" },
    { alternative_id: "a3", criterion_id: "grade", value: "Mid" },
  ],
});

const opNames = (ops: Operation[]) => ops.map((o) => o.op);

describe("renaming a label is one atomic request that keeps everything consistent", () => {
  it("renames in the scale, in the preference mapping and in every measurement using it", () => {
    const ops = opsRenameLabel(project, grade, 1, "Medium");
    if (!Array.isArray(ops)) throw new Error("expected operations");
    expect(opNames(ops)).toEqual(["set_scale", "set_value_function", "set_performance", "set_performance"]);
    expect(ops[0]).toMatchObject({ scale: { labels: ["Low", "Medium", "High"] } });
    expect(ops[1]).toMatchObject({ value_function: { mapping: { Low: 0, Medium: 0.5, High: 1 } } });
    expect(ops.slice(2)).toEqual([
      { op: "set_performance", alternative_id: "a1", criterion_id: "grade", value: "Medium" },
      { op: "set_performance", alternative_id: "a3", criterion_id: "grade", value: "Medium" },
    ]);
  });

  it("refuses empty and duplicate names with a message, and does nothing for an unchanged name", () => {
    expect(opsRenameLabel(project, grade, 1, "  ")).toEqual({ error: "A label cannot be empty." });
    expect(opsRenameLabel(project, grade, 1, "High")).toEqual({ error: "The label “High” already exists." });
    expect(opsRenameLabel(project, grade, 1, " Mid ")).toEqual([]);
    expect(opsRenameLabel(project, grade, 9, "x")).toEqual([]);
  });
});

describe("label list edits", () => {
  it("removing a label drops its preference entry and clears the measurements that used it", () => {
    const ops = opsRemoveLabel(project, grade, 1);
    expect(opNames(ops)).toEqual(["set_scale", "set_value_function", "clear_performance", "clear_performance"]);
    expect(ops[1]).toMatchObject({ value_function: { mapping: { Low: 0, High: 1 } } });
  });

  it("adding a label appends a fresh unique 'best' level", () => {
    const ops = opsAddLabel(grade);
    expect(ops[0]).toMatchObject({ scale: { labels: ["Low", "Mid", "High", "Level 4"] } });
    expect(ops[1]).toMatchObject({ value_function: { mapping: { "Level 4": 1 } } });
    const clash = node("g", null, 0, { scale: { ...ordinalScale, labels: ["Level 2", "x"] }, value_function: { kind: "qualitative", mapping: { "Level 2": 0, x: 1 } } });
    expect(opsAddLabel(clash)[0]).toMatchObject({ scale: { labels: ["Level 2", "x", "Level 3"] } });
  });

  it("moving swaps neighbours and refuses to leave the list", () => {
    expect(opsMoveLabel(grade, 0, 1)[0]).toMatchObject({ scale: { labels: ["Mid", "Low", "High"] } });
    expect(opsMoveLabel(grade, 0, -1)).toEqual([]);
    expect(opsMoveLabel(grade, 2, 1)).toEqual([]);
  });

  it("setting a preference value changes only that label", () => {
    expect(opsSetLabelValue(grade, "Mid", 0.4)[0]).toMatchObject({ value_function: { mapping: { Low: 0, Mid: 0.4, High: 1 } } });
    expect(opsSetLabelValue(node("n"), "x", 1)).toEqual([]);
  });
});

describe("scale and function edits", () => {
  const cost = node("cost", null, 0, { scale: ratioScale, value_function: { kind: "linear", direction: "decreasing", out_of_domain: "error" } });
  const withData = projectWith([cost], { performances: [{ alternative_id: "a", criterion_id: "cost", value: 3 }] });

  it("a type change across families clears the measurements first, then sets scale and function", () => {
    expect(opNames(opsChangeScaleType(withData, cost, "ordinal", META))).toEqual([
      "clear_criterion_performances",
      "set_scale",
      "set_value_function",
    ]);
  });

  it("a type change within a family does not clear anything", () => {
    expect(opNames(opsChangeScaleType(withData, cost, "interval", META))).toEqual(["set_scale", "set_value_function"]);
  });

  it("no measurements, nothing to clear", () => {
    expect(opNames(opsChangeScaleType(projectWith([cost]), cost, "ordinal", META))).toEqual(["set_scale", "set_value_function"]);
    expect(hasMeasurements(withData, "cost")).toBe(true);
    expect(hasMeasurements(withData, "other")).toBe(false);
  });

  it("patches keep the other scale fields; a criterion without a scale has nothing to patch", () => {
    expect(opsPatchScale(cost, { upper: 99 })[0]).toMatchObject({ scale: { type: "ratio", unit: "kg", lower: 0, upper: 99 } });
    expect(opsPatchScale(node("n"), { upper: 1 })).toEqual([]);
  });

  it("choosing another function kind uses that kind's defaults over the current bounds", () => {
    expect(opsSetKind(cost, "piecewise_linear")[0]).toMatchObject({
      value_function: { kind: "piecewise_linear", points: [{ x: 0, value: 0 }, { x: 10, value: 1 }] },
    });
    expect(opsSetKind(node("n"), "linear")).toEqual([]);
  });
});
