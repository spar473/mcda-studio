import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { EvidenceInspection } from "../../src/api/types";
import { EvidenceClaims } from "../../src/components/EvidenceClaims";
import { project } from "../results/fixture";
const claim = (id: string, alternative: string, description: string, review: null | "accepted" = null) => ({
  id, alternative_id: alternative, criterion_id: "cost", value: 8, unit: "kg",
  source: { name: `Source ${id}`, reference: "https://example.org/source", location: "page 2", date: "2026-10-31", description, classification: "independent" as const },
  origin: { kind: "human" as const, proposed_by: "Analyst", tool_id: null, tool_version: null },
  review: review ? { status: review, reviewer: "Reviewer", reviewed_at: "2026-11-01T00:00:00Z", note: "Checked", corrected_value: null } : null,
  uncertainty_lower: null, uncertainty_upper: null, outdated: false,
});
const result: EvidenceInspection = {
  dossier: { schema_version: 1, project_fingerprint: "fp", claims: [claim("first", "a", "Judgement: explicit rubric", "accepted"), claim("second", "b", "Observed: quotation")] },
  workspace: { workspace_version: 1, source_project: project, original_dossier: { schema_version: 1, project_fingerprint: "fp", claims: [] }, reviews: [], digest: "history" },
  preview: { project_fingerprint: "fp", evidence_digest: "evidence", review_digest: "review", changes: [], issues: [], missing_measurements: [],
    unreviewed_claims: ["second"], outdated_claims: ["first"], conflicting_cells: [{ alternative_id: "a", criterion_id: "cost" }] },
  support_available: true, workspace_exportable: true, support: [],
};
it("keeps overlapping backend tags distinct from review status, with sources and dates and IDs in Details", () => {
  const review = vi.fn(), before = structuredClone(result);
  const rendered = render(<EvidenceClaims result={result} project={project} stale={false} onReview={review} onMeasurement={vi.fn()}/>);
  const companies = rendered.container.querySelectorAll("details");
  expect(companies).toHaveLength(2); expect(companies[0]).toHaveAttribute("open"); expect(companies[1]).not.toHaveAttribute("open");
  expect(rendered.container.querySelectorAll("li[data-claim-id]")).toHaveLength(2);
  const row = rendered.container.querySelector('[data-claim-id="first"]') as HTMLElement;
  expect(row).toHaveTextContent("accepted · Disputed · Outdated · Judgement");
  expect(within(row).getByRole("link", { name: "Source first" })).toHaveAttribute("href", "https://example.org/source");
  expect(row).toHaveTextContent("2026-10-31"); expect(within(row).queryByText("first", { exact: true })).toBeNull();
  fireEvent.click(within(row).getByRole("button", { name: "Claim details for Source first" }));
  expect(within(row).getByText("first", { exact: true })).toBeVisible();
  for (const tag of ["Disputed", "Outdated", "Judgement"]) {
    fireEvent.click(screen.getByRole("button", { name: tag }));
    expect(rendered.container.querySelectorAll("li[data-claim-id]")).toHaveLength(1);
    expect(rendered.container.querySelector('[data-claim-id="first"]')).toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  expect(rendered.container.querySelectorAll("li[data-claim-id]")).toHaveLength(2);
  expect(result).toEqual(before); expect(review).not.toHaveBeenCalled();
});
