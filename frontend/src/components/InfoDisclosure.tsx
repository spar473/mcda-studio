import { useEffect, useLayoutEffect, useId, useRef, useState, type ReactNode } from "react";

/** Inline, keyboard-accessible detail. Closed diagnostics are not rendered. */
export function InfoDisclosure({ label = "Details", children }: { label?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false), id = useId();
  const [position, setPosition] = useState({ left: 8, top: 8, maxHeight: 320 });
  const root = useRef<HTMLSpanElement>(null), button = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = button.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(512, window.innerWidth - 16);
      const top = rect.bottom + 8 < window.innerHeight - 200 ? rect.bottom + 8 : Math.max(8, rect.top - 280);
      setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)), top, maxHeight: window.innerHeight - top - 12 });
    };
    place(); window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false); if (event instanceof KeyboardEvent) { event.preventDefault(); button.current?.focus(); }
      }
    };
    const focus = (event: FocusEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("keydown", close); document.addEventListener("pointerdown", close); document.addEventListener("focusin", focus);
    return () => { document.removeEventListener("keydown", close); document.removeEventListener("pointerdown", close); document.removeEventListener("focusin", focus); };
  }, [open]);
  return <span className="info-disclosure" ref={root} onKeyDown={event => {
    if (open && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); button.current?.focus(); }
  }}>
    <button type="button" className="link info-trigger" ref={button} aria-label={label} aria-expanded={open} aria-controls={id}
      onClick={event => { event.stopPropagation(); setOpen(!open); }}>ⓘ</button>
    {open && <span id={id} className="info-content" role="note" style={position}>{children}</span>}
  </span>;
}

export function Caveat({ caption, children, id }: { caption: string; children: ReactNode; id?: string }) {
  return <p className="muted small caveat" data-caveat={id}>{caption} <InfoDisclosure label={`About: ${caption}`}>{children}</InfoDisclosure></p>;
}
