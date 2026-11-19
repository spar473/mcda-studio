import { RESET_TRIAL } from "./WeightTrialGate";
import { createContext, useContext, type HTMLAttributes, type ReactNode, type SVGProps } from "react";
import type { Project } from "../api/types";
import { displayNumber } from "./results/numberDisplay";

/** A source/rubric ID join only. The displayed contribution is supplied by Python. */
export function ratingExplanation(project: Project, alternativeId: string, criterionId: string, contribution: number): string {
  const criterion = project.criteria.find(c => c.id === criterionId);
  const raw = project.performances.find(p => p.alternative_id === alternativeId && p.criterion_id === criterionId)?.value;
  const rubric = typeof raw === "string" ? raw : criterion?.description;
  return `${criterion?.name ?? criterionId} · contribution ${displayNumber(contribution)}. ${rubric || "No rubric text stated."}`;
}

export interface CompanyExploration {
  blocked?: boolean;
  open: (alternativeId: string, profileId?: string) => void;
  hint: (anchor: Element, alternativeId: string, criterionId: string, contribution: number) => void;
  clearHint: () => void;
}
export const CompanyExplorationContext = createContext<CompanyExploration | null>(null);
export const useCompanyExploration = () => useContext(CompanyExplorationContext);

/** One company action throughout analysis; standalone displays retain plain text. */
export function CompanyName({ id, children, profileId }: { id: string; children: ReactNode; profileId?: string }) {
  const exploration = useCompanyExploration();
  return exploration ? <button type="button" className="link company-name" aria-haspopup="dialog" data-company-id={id} disabled={exploration.blocked} title={exploration.blocked ? RESET_TRIAL : undefined}
    onClick={event => { event.stopPropagation(); exploration.open(id, profileId); }}>{children}</button> : <>{children}</>;
}

/** The company button is the row's single tab stop; other controls keep their own action. */
export function companyRow(exploration: CompanyExploration | null, id: string, profileId?: string, onSelect?: (id: string) => void): HTMLAttributes<HTMLTableRowElement> {
  if (!exploration || exploration.blocked) return {};
  const nested = (target: EventTarget | null) => target instanceof Element && Boolean(target.closest("button,a,input,select,textarea,summary,[role='button'],.info-disclosure,[role='note']"));
  const activate = (row: HTMLTableRowElement) => {
    row.querySelector<HTMLElement>('th[scope="row"] button')?.focus();
    onSelect?.(id); exploration.open(id, profileId);
  };
  return {
    onClick: event => { if (!nested(event.target)) activate(event.currentTarget); },
    onKeyDown: event => {
      if (!nested(event.target) && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault(); activate(event.currentTarget);
      }
    },
  };
}

export function companySvg(exploration: CompanyExploration | null, id: string, name: string): SVGProps<SVGGElement> {
  if (exploration?.blocked) return { role: "button", tabIndex: -1, "aria-disabled": true, "aria-label": `${name}: ${RESET_TRIAL}` };
  return exploration ? { role: "button", tabIndex: 0, "aria-label": `Open ${name} screening detail`,
    onClick: event => { event.currentTarget.focus(); exploration.open(id); },
    onKeyDown: event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); exploration.open(id); }
    },
  } : {};
}
