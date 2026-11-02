import { describe, expect, it } from "vitest";
import {
  allowedKinds,
  changeScaleType,
  defaultScale,
  defaultValueFunction,
  directionOf,
  evenMapping,
  parseNumber,
} from "../../src/model/defaults";
import { META, node, ordinalScale, ratioScale } from "../fixtures";

describe("parseNumber", () => {
  it.each([
    ["12", 12],
    ["-0.5", -0.5],
    [" +3.25 ", 3.25],
    [".5", 0.5],
    ["1e3", 1000],
    ["", null],
    ["   ", null],
  ])("accepts %j", (text, value) => {
    expect(parseNumber(text)).toBe(value);
  });
  it.each(["abc", "1,5", "1 2", "--1", "1e", "NaN", "Infinity", "0x10", "1e999"])("rejects %j", (text) => {
    expect(parseNumber(text)).toBeUndefined();
  });
});

describe("measurement-type changes", () => {
  it("only the server's meta decides which kinds are allowed", () => {
    expect(allowedKinds(META, "ratio")).toEqual(["linear", "piecewise_linear"]);
    expect(allowedKinds(META, "ordinal")).toEqual(["qualitative"]);
    expect(allowedKinds({ ...META, scale_types: [] }, "ratio")).toEqual([]);
  });

  it("a first choice of type gives a usable default, and clears nothing", () => {
    const c = changeScaleType(node("x"), "ratio", META);
    expect(c.scale).toMatchObject({ type: "ratio", lower: 0, upper: 100, anchor_mode: "fixed" });
    expect(c.valueFunction.kind).toBe("linear");
    expect(c.clearsMeasurements).toBe(false);
  });

  it("ratio to interval keeps bounds and unit, and a function that is still allowed", () => {
    const n = node("x", null, 0, { scale: ratioScale, value_function: { kind: "linear", direction: "decreasing", out_of_domain: "clamp" } });
    const c = changeScaleType(n, "interval", META);
    expect(c.scale).toMatchObject({ type: "interval", unit: "kg", lower: 0, upper: 10 });
    expect(c.valueFunction).toEqual({ kind: "linear", direction: "decreasing", out_of_domain: "clamp" });
    expect(c.clearsMeasurements).toBe(false);
  });

  it("numeric to labelled switches family: new defaults, and entered measurements are cleared", () => {
    const n = node("x", null, 0, { scale: ratioScale });
    const c = changeScaleType(n, "ordinal", META);
    expect(c.scale.labels).toEqual(["Low", "Medium", "High"]);
    expect(c.valueFunction).toEqual({ kind: "qualitative", mapping: { Low: 0, Medium: 0.5, High: 1 } });
    expect(c.clearsMeasurements).toBe(true);
  });

  it("ordinal to categorical keeps the labels", () => {
    const n = node("x", null, 0, { scale: ordinalScale, value_function: { kind: "qualitative", mapping: { Low: 0, Mid: 0.2, High: 1 } } });
    const c = changeScaleType(n, "categorical", META);
    expect(c.scale.labels).toEqual(["Low", "Mid", "High"]);
    expect(c.valueFunction).toEqual({ kind: "qualitative", mapping: { Low: 0, Mid: 0.2, High: 1 } });
    expect(c.clearsMeasurements).toBe(false);
  });
});

describe("defaults", () => {
  it("piecewise defaults run from the lower to the upper bound", () => {
    expect(defaultValueFunction("piecewise_linear", ratioScale)).toEqual({
      kind: "piecewise_linear",
      points: [
        { x: 0, value: 0 },
        { x: 10, value: 1 },
      ],
      out_of_domain: "error",
    });
  });
  it("evenMapping spreads preference values from 0 to 1", () => {
    expect(evenMapping(["a", "b", "c", "d", "e"])).toEqual({ a: 0, b: 0.25, c: 0.5, d: 0.75, e: 1 });
    expect(evenMapping(["only"])).toEqual({ only: 0 });
  });
  it("defaultScale distinguishes numeric from labelled", () => {
    expect(defaultScale("interval").labels).toEqual([]);
    expect(defaultScale("categorical").lower).toBeNull();
  });
});

describe("directionOf (display only)", () => {
  it("reads linear, piecewise and qualitative functions", () => {
    expect(directionOf({ kind: "linear", direction: "decreasing", out_of_domain: "error" })).toBe("decreasing");
    expect(directionOf({ kind: "direct_rating", min_rating: 0, max_rating: 10, out_of_domain: "error" })).toBe("increasing");
    const pw = (v: number[]) => ({ kind: "piecewise_linear" as const, out_of_domain: "error" as const, points: v.map((value, i) => ({ x: i, value })) });
    expect(directionOf(pw([0, 0.5, 1]))).toBe("increasing");
    expect(directionOf(pw([1, 0.4, 0]))).toBe("decreasing");
    expect(directionOf(pw([0, 1, 0]))).toBe("mixed");
    expect(directionOf(pw([0.5, 0.5]))).toBe("mixed"); // flat cannot satisfy worst = 0, best = 1
    expect(directionOf({ ...pw([0, 1]), points: [{ x: 0, value: 0 }] })).toBeNull(); // too few points
    const q = { kind: "qualitative" as const, mapping: { a: 1, b: 0.5, c: 0 } };
    expect(directionOf(q, ["a", "b", "c"])).toBe("decreasing");
    expect(directionOf(q, ["c", "b", "a"])).toBe("increasing");
    expect(directionOf(q, ["a"])).toBeNull();
  });
});
