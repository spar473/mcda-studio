import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../src/api/client";

function respond(status: number, body?: unknown, statusText = ""): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(body === undefined ? null : typeof body === "string" ? body : JSON.stringify(body), {
          status,
          statusText,
        }),
      ),
    ),
  );
}
const lastCall = (): [string, RequestInit] => {
  const calls = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
  const last = calls[calls.length - 1];
  if (!last) throw new Error("fetch was not called");
  return last;
};

afterEach(() => vi.unstubAllGlobals());

describe("error handling", () => {
  it("turns the server's standard error body into an ApiError", async () => {
    respond(422, { error: { code: "MODEL_STRUCTURE", message: "cycle", details: [{ path: "criteria[a]", message: "x" }] } });
    const e = await api.getProject("p").catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 422, code: "MODEL_STRUCTURE", message: "cycle", details: [{ path: "criteria[a]", message: "x" }] });
  });

  it("an error without the standard body still says what happened", async () => {
    respond(502, "<html>bad gateway</html>", "Bad Gateway");
    const e = (await api.getProject("p").catch((x: unknown) => x)) as ApiError;
    expect(e.code).toBe("HTTP_502");
    expect(e.message).toContain("502");
  });

  it("an unreachable server is reported as such, not as a crash", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const e = (await api.health().catch((x: unknown) => x)) as ApiError;
    expect(e).toMatchObject({ status: 0, code: "NETWORK" });
    expect(e.message).toContain("mcda serve");
  });
});

describe("requests", () => {
  it("saving sends the project with the revision it was based on as If-Match", async () => {
    respond(200, { project: {}, fingerprint: "f", validation: { issues: [] } });
    await api.saveProject({ id: "my id" } as never, "abc");
    const [url, init] = lastCall();
    expect(url).toBe("/api/projects/my%20id");
    expect(init.method).toBe("PUT");
    expect((init.headers as Record<string, string>)["If-Match"]).toBe('"abc"');
    expect(init.body).toBe(JSON.stringify({ id: "my id" }));
  });

  it("a 204 (delete) resolves to undefined", async () => {
    respond(204);
    await expect(api.deleteProject("p")).resolves.toBeUndefined();
    expect(lastCall()[1].method).toBe("DELETE");
  });

  it("edit posts the working copy and the operation list together", async () => {
    respond(200, { project: {}, fingerprint: "f", validation: { issues: [] } });
    await api.edit({ id: "p" } as never, [{ op: "add_alternative", name: "A" }]);
    const [url, init] = lastCall();
    expect(url).toBe("/api/edit");
    expect(JSON.parse(init.body as string)).toEqual({ project: { id: "p" }, operations: [{ op: "add_alternative", name: "A" }] });
  });

  it("import passes the conflict policy; ids are url-encoded", async () => {
    respond(201, { project: {}, fingerprint: "f", validation: { issues: [] } });
    await api.importProject({ a: 1 }, "new_id");
    expect(lastCall()[0]).toBe("/api/projects/import?on_conflict=new_id");
    expect(api.downloadUrl("a/b")).toBe("/api/projects/a%2Fb/file");
  });
});
