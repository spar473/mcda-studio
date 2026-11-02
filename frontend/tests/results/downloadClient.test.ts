import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnalysisExportRequest } from "../../src/api/types";
import { project } from "./fixture";

const request: AnalysisExportRequest = { project, expected_project_fingerprint: "a".repeat(64), expected_record_digest: "b".repeat(64), format: "json", table: "ranking" };
afterEach(() => vi.unstubAllGlobals());
function respond(headers: Record<string, string>) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { headers: {
    "Content-Type": "application/json", "Content-Disposition": 'attachment; filename="mcda-export.json"',
    "X-Project-Fingerprint": request.expected_project_fingerprint, "X-Analysis-Record-Digest": request.expected_record_digest, ...headers,
  } }))));
}
it("accepts only a download whose revision/digest/MIME/filename match the captured request", async () => {
  respond({}); const signal = new AbortController().signal; const file = await api.exportAnalysis(request, signal);
  expect(file.filename).toBe("mcda-export.json"); expect(await file.blob.text()).toBe("{}");
  expect(fetch).toHaveBeenCalledWith("/api/analysis/export", expect.objectContaining({ signal, method: "POST" }));
});
const variations: Record<string, string>[] = [
  { "X-Project-Fingerprint": "wrong" }, { "X-Analysis-Record-Digest": "wrong" },
  { "Content-Type": "text/html" }, { "Content-Disposition": 'attachment; filename="../bad.json"' },
];
it.each(variations)("rejects mismatched download metadata %j", async headers => {
  respond(headers); await expect(api.exportAnalysis(request)).rejects.toThrow(/does not match|unexpected|did not identify/);
});
