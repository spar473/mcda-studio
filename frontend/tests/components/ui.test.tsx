import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Banner, CommitNumber, CommitText, ConfirmDialog } from "../../src/components/ui";

describe("CommitNumber", () => {
  function setup(value: number | null = 5, allowEmpty = false) {
    const onCommit = vi.fn();
    render(<CommitNumber label="Weight" value={value} onCommit={onCommit} allowEmpty={allowEmpty} />);
    return { onCommit, input: screen.getByLabelText("Weight"), user: userEvent.setup() };
  }

  it("commits a valid number on Enter, not while typing", async () => {
    const { onCommit, input, user } = setup();
    await user.clear(input);
    await user.type(input, "7.5");
    expect(onCommit).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(7.5);
  });

  it("commits on blur too", async () => {
    const { onCommit, input, user } = setup();
    await user.clear(input);
    await user.type(input, "12");
    await user.tab();
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(12);
  });

  it("does not commit an unchanged value", async () => {
    const { onCommit, input, user } = setup();
    await user.click(input);
    await user.tab();
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("rejects text that is not a number: nothing is committed and the field is marked invalid", async () => {
    const { onCommit, input, user } = setup();
    await user.clear(input);
    await user.type(input, "12 apples");
    await user.keyboard("{Enter}");
    expect(onCommit).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveValue("12 apples"); // the user's text is kept so they can fix it
  });

  it("an emptied field is an error unless empty is allowed, in which case it commits null", async () => {
    const a = setup(5, false);
    await a.user.clear(a.input);
    await a.user.keyboard("{Enter}");
    expect(a.onCommit).not.toHaveBeenCalled();
    expect(a.input).toHaveAttribute("aria-invalid", "true");

    document.body.innerHTML = "";
    const b = setup(5, true);
    await b.user.clear(b.input);
    await b.user.keyboard("{Enter}");
    expect(b.onCommit).toHaveBeenCalledExactlyOnceWith(null);
  });

  it("Escape restores the stored value", async () => {
    const { onCommit, input, user } = setup();
    await user.clear(input);
    await user.type(input, "99");
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("5");
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("follows the stored value when it changes from outside (undo, server round trip)", () => {
    const { rerender } = render(<CommitNumber label="W" value={1} onCommit={() => undefined} />);
    rerender(<CommitNumber label="W" value={2} onCommit={() => undefined} />);
    expect(screen.getByLabelText("W")).toHaveValue("2");
  });
});

describe("CommitText", () => {
  it("commits on Enter; a required field cannot be emptied", async () => {
    const onCommit = vi.fn();
    render(<CommitText label="Name" value="Alpha" required onCommit={onCommit} />);
    const input = screen.getByLabelText("Name");
    const user = userEvent.setup();
    await user.clear(input);
    await user.keyboard("{Enter}");
    expect(onCommit).not.toHaveBeenCalled();
    expect(input).toHaveValue("Alpha"); // reverted
    await user.clear(input);
    await user.type(input, "Beta{Enter}");
    expect(onCommit).toHaveBeenCalledExactlyOnceWith("Beta");
  });

  it("Escape discards the edit", async () => {
    const onCommit = vi.fn();
    render(<CommitText label="Name" value="Alpha" onCommit={onCommit} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Name"), "zzz{Escape}");
    expect(screen.getByLabelText("Name")).toHaveValue("Alpha");
    expect(onCommit).not.toHaveBeenCalled();
  });

  describe("focus requests", () => {
    function Harness({ disabled = false, focusKey = 0 }: { disabled?: boolean; focusKey?: number }) {
      return (
        <>
          <button type="button">Elsewhere</button>
          <CommitText label="Title" value="Alpha" disabled={disabled} focusKey={focusKey} onCommit={() => undefined} />
        </>
      );
    }

    it("focuses and selects the text when asked", () => {
      render(<Harness focusKey={1} />);
      const input = screen.getByLabelText<HTMLInputElement>("Title");
      expect(input).toHaveFocus();
      expect([input.selectionStart, input.selectionEnd]).toEqual([0, 5]);
    });

    it("waits while the field is disabled, then takes focus once it is enabled", () => {
      const { rerender } = render(<Harness disabled focusKey={1} />);
      expect(screen.getByLabelText("Title")).not.toHaveFocus();
      rerender(<Harness focusKey={1} />);
      expect(screen.getByLabelText("Title")).toHaveFocus();
    });

    it("does not steal focus from a control the user has moved to in the meantime", async () => {
      const { rerender } = render(<Harness disabled focusKey={1} />);
      await userEvent.setup().click(screen.getByRole("button", { name: "Elsewhere" }));
      rerender(<Harness focusKey={1} />);
      expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
    });

    it("drops a waiting request when it is withdrawn", () => {
      const { rerender } = render(<Harness disabled focusKey={1} />);
      rerender(<Harness disabled focusKey={0} />);
      rerender(<Harness focusKey={0} />);
      expect(screen.getByLabelText("Title")).not.toHaveFocus();
    });

    it("answers each request once: a later busy period does not pull focus back", async () => {
      const { rerender } = render(<Harness focusKey={1} />);
      await userEvent.setup().click(screen.getByRole("button", { name: "Elsewhere" }));
      rerender(<Harness disabled focusKey={1} />);
      rerender(<Harness focusKey={1} />);
      expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
    });
  });
});

describe("ConfirmDialog", () => {
  it("is a labelled modal dialog; Escape cancels; the buttons do what they say", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmDialog title="Remove it?" message="really" confirmLabel="Remove" onConfirm={onConfirm} onCancel={onCancel} />);
    const dialog = screen.getByRole("dialog", { name: "Remove it?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const user = userEvent.setup();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("Banner", () => {
  it("errors are announced as alerts, information as status", () => {
    render(
      <>
        <Banner kind="error">bad</Banner>
        <Banner kind="info">fyi</Banner>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("bad");
    expect(screen.getByRole("status")).toHaveTextContent("fyi");
  });
});
