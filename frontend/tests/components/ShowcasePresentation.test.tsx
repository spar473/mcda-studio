import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IssueText, MessageText } from "../../src/components/IssueText";
import { InfoDisclosure } from "../../src/components/InfoDisclosure";
import { ValidationPanel } from "../../src/components/ValidationPanel";
import { displayFixed, displayNumber } from "../../src/components/results/numberDisplay";
import { Modal } from "../../src/components/ui";
import { CommitNumber } from "../../src/components/ui";

describe("quiet, inspectable presentation", () => {
  it("keeps codes and paths out of the initial message and returns focus on Escape", () => {
    render(<IssueText code="OUT_OF_DOMAIN" message="Outside the stated range" path="performances[a,c]"/>);
    expect(screen.getByText("Outside the stated range")).toBeVisible();
    expect(screen.queryByText("OUT_OF_DOMAIN")).toBeNull(); expect(screen.queryByText("performances[a,c]")).toBeNull();
    const button = screen.getByRole("button", { name: "Details for this message" });
    expect(button).toHaveAttribute("aria-expanded", "false"); button.focus(); fireEvent.click(button);
    expect(screen.getByText("OUT_OF_DOMAIN")).toBeVisible(); expect(screen.getByText("performances[a,c]")).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button).toHaveFocus(); expect(screen.queryByText("OUT_OF_DOMAIN")).toBeNull();
  });
  it("moves a service refusal's diagnostic prefix into Details without losing its explanation", () => {
    render(<MessageText message="CALCULATION_ACCEPT_INVALID: Formula dimensions differ."/>);
    expect(screen.getByText("Formula dimensions differ.")).toBeVisible(); expect(screen.queryByText("CALCULATION_ACCEPT_INVALID")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Details for this message" }));
    expect(screen.getByText("CALCULATION_ACCEPT_INVALID")).toBeVisible();
  });
  it("closes details on an outside pointer action", () => {
    render(<><InfoDisclosure label="Context details">Full provenance</InfoDisclosure><button>Elsewhere</button></>);
    fireEvent.click(screen.getByRole("button", { name: "Context details" }));
    expect(screen.getByText("Full provenance")).toBeVisible();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByText("Full provenance")).toBeNull();
  });
  it("Escape closes its own disclosure before its parent dialog", () => {
    const close = vi.fn();
    render(<Modal title="Inspector" onClose={close}><InfoDisclosure label="Diagnostic details">Full diagnostic</InfoDisclosure></Modal>);
    const button = screen.getByRole("button", { name: "Diagnostic details" });
    fireEvent.click(button); fireEvent.keyDown(button, { key: "Escape" });
    expect(screen.queryByText("Full diagnostic")).toBeNull(); expect(close).not.toHaveBeenCalled(); expect(button).toHaveFocus();
    fireEvent.keyDown(button, { key: "Escape" }); expect(close).toHaveBeenCalledOnce();
  });
  it("omits zero badges and retains nonzero repair actions and diagnostics", () => {
    const go = vi.fn(), view = render(<ValidationPanel report={{ issues: [] }} onGo={go}/>);
    expect(screen.getByText("Model complete")).toBeVisible(); expect(view.container.querySelectorAll(".badge")).toHaveLength(0);
    const issue = { code: "MISSING_MEASUREMENT", severity: "error" as const, message: "Enter the missing measurement", path: "performances[a,c]" };
    view.rerender(<ValidationPanel report={{ issues: [issue] }} onGo={go}/>);
    expect(screen.getByLabelText("1 errors")).toHaveTextContent("1"); expect(screen.queryByLabelText("0 warnings")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Enter the missing measurement/ })); expect(go).toHaveBeenCalledWith(issue);
    expect(screen.queryByText(issue.code)).toBeNull(); fireEvent.click(screen.getByRole("button", { name: "Details for this message" }));
    expect(screen.getByText(issue.code)).toBeVisible();
  });
  it("rounds only the displayed baseline and never commits untouched rounded text", () => {
    const commit = vi.fn(), value = .3333333333333333;
    render(<CommitNumber label="Weight" value={value} displayText={displayNumber(value)} onCommit={commit}/>);
    const input = screen.getByLabelText("Weight"); expect(input).toHaveValue("0.3333");
    fireEvent.blur(input); fireEvent.keyDown(input, { key: "Enter" }); expect(commit).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "0.123456789" } }); fireEvent.blur(input);
    expect(commit).toHaveBeenCalledWith(.123456789);
  });
  it.each([.000000001, -.000000001, .00009999, 0, .0001, .3456789, 1e22])("never uses scientific notation for primary value %s", value => {
    expect(displayNumber(value)).not.toMatch(/[eE][+-]?\d/);
    expect(displayNumber(value, "full")).not.toMatch(/[eE][+-]?\d/);
    if (value !== 0 && Math.abs(value) < .0001) expect(displayNumber(value)).toBe(`${value < 0 ? "−" : ""}< 0.0001`);
    for (const digits of [2, 3]) {
      expect(displayFixed(value, digits)).not.toMatch(/[eE][+-]?\d/);
      if (value !== 0 && Math.abs(value) < .0001) expect(displayFixed(value, digits)).toBe(`${value < 0 ? "−" : ""}< 0.0001`);
    }
  });
});
