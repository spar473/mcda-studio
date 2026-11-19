import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MeasurementEditor } from "../../src/components/MeasurementEditor";
import { META, node, projectWith, ratioScale } from "../fixtures";

describe("measurement edits remain separate while a server edit is pending", () => {
  it("blocks overlapping whole-scale commits until the previous revision arrives", () => {
    const criterion = node("cost", null, 0, { scale: ratioScale,
      value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } });
    const props = { project: projectWith([criterion]), node: criterion, meta: META,
      apply: vi.fn(() => Promise.resolve(true)) };
    const { rerender } = render(<MeasurementEditor {...props} busy={true} />);
    expect(screen.getByLabelText("Lower bound")).toBeDisabled();
    expect(screen.getByLabelText("Upper bound")).toBeDisabled();
    expect(screen.getByLabelText("Unit")).toBeDisabled();
    rerender(<MeasurementEditor {...props} busy={false} />);
    expect(screen.getByLabelText("Lower bound")).toBeEnabled();
  });
});
