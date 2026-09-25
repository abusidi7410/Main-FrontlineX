import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, setAccessToken } from "../client";

afterEach(() => {
  setAccessToken(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("apiFetch request bodies", () => {
  it("sends FormData unchanged and lets the browser set its boundary", async () => {
    const formData = new FormData();
    formData.append("file", new Blob(["first_name\nAda\n"], { type: "text/csv" }), "students.csv");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/students/import/analyse", { method: "POST", body: formData });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.body).toBe(formData);
    expect(new Headers(request.headers).get("Content-Type")).toBeNull();
  });

  it("keeps JSON requests explicitly serialized", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/students", { method: "POST", body: { firstName: "Ada" } });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.body).toBe(JSON.stringify({ firstName: "Ada" }));
    expect(new Headers(request.headers).get("Content-Type")).toBe("application/json");
  });
});
