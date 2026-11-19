import { useId, useState, type ReactNode } from "react";

/** The same explanation on pointer hover and keyboard focus; no derived score. */
export function RatingHint({ text, children }: { text: string; children: ReactNode }) {
  const id = useId();
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const show = (anchor: HTMLElement) => {
    const rect = anchor.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - Math.min(480, window.innerWidth - 16) - 8)),
      top: rect.bottom < window.innerHeight - 190 ? rect.bottom + 8 : Math.max(8, rect.top - 180) });
  };
  return <span className="rating-hint" tabIndex={0} aria-describedby={position ? id : undefined}
    onMouseEnter={event => show(event.currentTarget)} onFocus={event => show(event.currentTarget)}
    onMouseLeave={event => { if (!event.currentTarget.contains(document.activeElement)) setPosition(null); }}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setPosition(null); }}
    onKeyDown={event => { if (event.key === "Escape" && position) { event.stopPropagation(); setPosition(null); } }}>
    {children}{position && <span id={id} role="tooltip" className="rating-tooltip" style={position}>{text}</span>}
  </span>;
}
