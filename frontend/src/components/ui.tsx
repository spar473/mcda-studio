import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { parseNumber } from "../model/defaults";

// ---- modal dialogs ---------------------------------------------------------------------------
function modalFocusables(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return [...root.querySelectorAll<HTMLElement>("input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], summary, [tabindex='0']")].filter(element => {
    if (element.tabIndex < 0 || element.closest("[hidden],[inert]")) return false;
    for (let parent: HTMLElement | null = element; parent && parent !== root; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return false;
      if (parent instanceof HTMLDetailsElement && !parent.open && !parent.querySelector(":scope > summary")?.contains(element)) return false;
    }
    return true;
  });
}

export function Modal(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  className?: string;
  closeLabel?: string;
  onFocusFallback?: () => void;
}) {
  const { title, onClose, children, footer, wide } = props;
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const fallback = useRef(props.onFocusFallback);
  useEffect(() => {
    const onMissing = fallback.current;
    const previous = document.activeElement as HTMLElement | null;
    modalFocusables(ref.current)[0]?.focus();
    return () => {
      if (previous?.isConnected && previous !== document.body && !previous.closest("[hidden],[inert]")) previous.focus();
      else onMissing?.();
    };
  }, []);
  // Loading can remove the focused control. Keep Escape and Tab working from body
  // without re-running the mount/restore effect or stealing focus inside this dialog.
  useEffect(() => {
    const onOutsideKey = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
      if (dialogs[dialogs.length - 1] !== ref.current) return;
      if (ref.current.contains(document.activeElement)) return;
      if (event.key === "Escape") { event.stopPropagation(); onClose(); }
      else if (event.key === "Tab") {
        event.preventDefault();
        const items = modalFocusables(ref.current);
        (event.shiftKey ? items[items.length - 1] : items[0])?.focus();
      }
    };
    document.addEventListener("keydown", onOutsideKey);
    return () => document.removeEventListener("keydown", onOutsideKey);
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={ref} className={`modal${wide ? " wide" : ""} ${props.className ?? ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId}
      onKeyDown={event => {
        if (event.key === "Tab") {
          const items = modalFocusables(ref.current), first = items[0], last = items[items.length - 1];
          if (!items.length) event.preventDefault();
          else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
        if (event.key === "Escape") { event.stopPropagation(); onClose(); }
      }}>
      <h2 id={titleId}>{title}</h2>
      {props.closeLabel && <button type="button" className="modal-dismiss" aria-label={props.closeLabel} onClick={onClose}>×</button>}
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-footer">{footer}</div>}
    </div>
  </div>;
}

export function ConfirmDialog(props: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  extra?: ReactNode;
}) {
  return (
    <Modal
      title={props.title}
      onClose={props.onCancel}
      footer={
        <>
          {props.extra}
          <button type="button" onClick={props.onCancel}>
            {props.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            className={props.danger ? "danger" : "primary"}
            onClick={props.onConfirm}
          >
            {props.confirmLabel}
          </button>
        </>
      }
    >
      <div>{props.message}</div>
    </Modal>
  );
}

// ---- inputs that commit on blur / Enter ------------------------------------------------------
export function CommitText(props: {
  label: string;
  value: string;
  onCommit: (value: string) => void;
  multiline?: boolean;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  selectOnFocus?: boolean;
  /** Increment to move keyboard focus (and select the text) into this field. */
  focusKey?: number;
}) {
  const { label, value, onCommit, multiline, required, disabled, placeholder, focusKey } = props;
  const [draft, setDraft] = useState(value);
  const [seen, setSeen] = useState(value);
  if (value !== seen) {
    // the stored value changed from outside (undo, a server round trip): show it
    setSeen(value);
    setDraft(value);
  }
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  // Escape resets the draft and then blurs; the blur handler still sees the old draft (state
  // updates apply after the handler), so it must be told not to commit it.
  const cancelled = useRef(false);
  // A focus request aimed at a disabled field (the edit started by the previous field's blur may
  // still be pending) waits until the field is enabled, unless focus has moved to another control
  // meanwhile. It holds the element that had focus when the request arrived; undefined: no request.
  const pendingFocus = useRef<Element | null | undefined>(undefined);
  useEffect(() => {
    pendingFocus.current = focusKey && focusKey > 0 ? document.activeElement : undefined;
  }, [focusKey]);
  useEffect(() => {
    if (disabled || pendingFocus.current === undefined) return;
    const requestedFrom = pendingFocus.current;
    pendingFocus.current = undefined;
    const active = document.activeElement;
    if (active && active !== document.body && active !== requestedFrom) return;
    ref.current?.focus();
    ref.current?.select();
  }, [focusKey, disabled]);

  const commit = () => {
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    if (draft === value) return;
    if (required && draft.trim() === "") {
      setDraft(value);
      return;
    }
    onCommit(draft);
  };
  const common = {
    "aria-label": label,
    value: draft,
    disabled,
    placeholder,
    className: props.className,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(e.target.value),
    onBlur: commit,
    onFocus: props.selectOnFocus
      ? (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => e.target.select()
      : undefined,
  };
  return multiline ? (
    <textarea
      {...common}
      rows={3}
      ref={ref}
      onKeyDown={(e) => {
        if (e.key === "Escape") setDraft(value);
      }}
    />
  ) : (
    <input
      {...common}
      type="text"
      ref={ref}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          cancelled.current = true;
          setDraft(value);
          e.currentTarget.blur();
        }
      }}
    />
  );
}

export function formatNumber(n: number): string {
  return String(n);
}

export function CommitNumber(props: {
  label: string;
  value: number | null;
  onCommit: (value: number | null) => void;
  allowEmpty?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  invalid?: boolean;
  inputId?: string;
  displayText?: string;
}) {
  const { label, value, onCommit, allowEmpty, disabled } = props;
  const shown = props.displayText ?? (value === null ? "" : formatNumber(value));
  const [draft, setDraft] = useState(shown);
  const [bad, setBad] = useState(false);
  const [seen, setSeen] = useState(shown);
  if (shown !== seen) {
    setSeen(shown);
    setDraft(shown);
    setBad(false);
  }
  const cancelled = useRef(false); // see CommitText: Escape must not commit the draft it discards

  const commit = () => {
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    if (draft === shown) {
      setBad(false);
      return;
    }
    const parsed = parseNumber(draft);
    if (parsed === undefined || (parsed === null && !allowEmpty)) {
      setBad(true);
      return;
    }
    setBad(false);
    onCommit(parsed);
  };
  return (
    <input
      id={props.inputId}
      type="text"
      inputMode="decimal"
      className={`num ${props.className ?? ""}`}
      aria-label={label}
      aria-invalid={bad || props.invalid ? true : undefined}
      title={bad ? "Enter a number" : undefined}
      value={draft}
      disabled={disabled}
      placeholder={props.placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          cancelled.current = true;
          setDraft(shown);
          setBad(false);
          e.currentTarget.blur();
        }
      }}
    />
  );
}

// ---- small pieces ----------------------------------------------------------------------------
export function Field(props: { label: string; hint?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label htmlFor={props.htmlFor}>{props.label}</label>
      {props.children}
      {props.hint && <div className="hint">{props.hint}</div>}
    </div>
  );
}

export function Banner(props: {
  kind: "error" | "info" | "warning";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div className={`banner ${props.kind}`} role={props.kind === "error" ? "alert" : "status"}>
      <div>{props.children}</div>
      {props.onDismiss && (
        <button type="button" className="link" onClick={props.onDismiss} aria-label="Dismiss message">
          ✕
        </button>
      )}
    </div>
  );
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
