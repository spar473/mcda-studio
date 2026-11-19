import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import * as downloads from "../../src/components/results/downloads";
import { ScreeningReportButton } from "../../src/components/results/ScreeningReportButton";
import type { AnalysisContext } from "../../src/state/analysisContext";
import { projectWith, node } from "../fixtures";

afterEach(() => { vi.restoreAllMocks(); });

const project = { ...projectWith([node("c")]), alternatives: [{ id: "a", name: "A", metadata: {} }] };
const context = {
  fingerprint: "fp", configuration: { method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} },
  resolvedProfileId: null, scenarioId: null, profileId: null, criterionId: null, method: null, parameters: null,
} as unknown as AnalysisContext;
const file = () => Promise.resolve({ blob: new Blob(["<html></html>"]), filename: "screening-report.html" });

it("downloads one report for the displayed revision and sends the project, configuration and dossier", async () => {
  const request = vi.spyOn(api, "exportScreeningReport").mockImplementation(file);
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const dossier = { schema_version: 1, project_fingerprint: "x", claims: [] };
  render(<ScreeningReportButton project={project} context={context} dossier={dossier as never} trial={{ active: false, generation: 0 }}/>);
  fireEvent.click(screen.getByRole("button", { name: "Download screening report" }));
  await waitFor(() => expect(save).toHaveBeenCalledOnce());
  expect(request).toHaveBeenCalledOnce();
  const [body, fingerprint] = request.mock.calls[0] ?? [];
  expect(fingerprint).toBe("fp"); expect(body?.project).toEqual(project); expect(body?.configuration).toEqual(context.configuration); expect(body?.dossier).toEqual(dossier);
  expect(save.mock.calls[0]?.[1]).toBe("screening-report.html");
});

it("is disabled with the Reset message during a what-if trial and sends nothing", () => {
  const request = vi.spyOn(api, "exportScreeningReport").mockImplementation(file);
  render(<ScreeningReportButton project={project} context={context} trial={{ active: true, generation: 1 }}/>);
  const button = screen.getByRole("button", { name: "Download screening report" });
  expect(button).toBeDisabled();
  expect(screen.getByText("Reset what-if to download the saved model")).toBeVisible();
  fireEvent.click(button); expect(request).not.toHaveBeenCalled();
});

it("an in-flight report can never be saved after a trial starts or Reset changes the generation", async () => {
  let release: (value: { blob: Blob; filename: string }) => void = () => undefined;
  vi.spyOn(api, "exportScreeningReport").mockImplementation(() => new Promise(resolve => { release = resolve; }));
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const { rerender } = render(<ScreeningReportButton project={project} context={context} trial={{ active: false, generation: 0 }}/>);
  fireEvent.click(screen.getByRole("button", { name: "Download screening report" }));
  rerender(<ScreeningReportButton project={project} context={context} trial={{ active: true, generation: 0 }}/>);
  rerender(<ScreeningReportButton project={project} context={context} trial={{ active: false, generation: 1 }}/>);
  release({ blob: new Blob(["x"]), filename: "screening-report.html" });
  await new Promise(resolve => setTimeout(resolve, 20));
  expect(save).not.toHaveBeenCalled();
});

it("shows a failure and never saves, and does nothing for a project without alternatives", async () => {
  vi.spyOn(api, "exportScreeningReport").mockRejectedValue(new Error("The server refused the report."));
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const { rerender } = render(<ScreeningReportButton project={project} context={context} trial={{ active: false, generation: 0 }}/>);
  fireEvent.click(screen.getByRole("button", { name: "Download screening report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The server refused the report.");
  expect(save).not.toHaveBeenCalled();
  rerender(<ScreeningReportButton project={{ ...project, alternatives: [] }} context={context} trial={{ active: false, generation: 0 }}/>);
  expect(screen.getByRole("button", { name: "Download screening report" })).toBeDisabled();
});
