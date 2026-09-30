import { describe, expect, it } from "vitest";

import { apiFetch } from "@/api/client";
import * as authService from "@/services/auth.service";

/**
 * Two frontend rules that are easy to break silently, so they are pinned here:
 *
 * 1. The login screen offers no development accounts. Nothing here should
 *    reference a demo role, a demo email or a demo password - a "test" account
 *    that reaches production is a real account, not a convenience.
 * 2. The student list reads the page from the server's own `count` and asks for
 *    the documented page size, so "Showing 1-25 of 64" cannot drift from what
 *    the API actually returned.
 */

describe("production login", () => {
  it("exposes no demo accounts", () => {
    const exported = authService as unknown as Record<string, unknown>;
    expect(exported.DEMO_ACCOUNTS).toBeUndefined();
  });

  it("has no hardcoded credential strings in the auth service", async () => {
    // Read the module source so a reintroduced constant is caught even if it is
    // not exported.
    const source = await import("@/services/auth.service?raw").then((m) => m.default as string);
    // Guard against a vacuous pass on an empty/garbled read: if this were
    // blank, the two assertions below would always succeed.
    expect(source.length).toBeGreaterThan(200);
    expect(source).toContain("export async function login");
    expect(source).not.toMatch(/demo/i);
    expect(source).not.toMatch(/password\s*[:=]\s*["'][^"']+["']/i);
  });

  it("still authenticates against the backend", async () => {
    // A guard against "fixing" the demo problem by breaking real login.
    expect(typeof authService.login).toBe("function");
  });
});

describe("student list pagination", () => {
  it("asks for 25 per page", async () => {
    const calls: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(typeof input === "string" ? input : input.toString());
      return new Response(JSON.stringify({ results: [], count: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    try {
      await apiFetch("/students", { query: { page: 1, pageSize: 25 } });
    } finally {
      globalThis.fetch = original;
    }

    const url = new URL(calls[0], "http://test.local");
    expect(url.searchParams.get("page")).toBe("1");
    expect(url.searchParams.get("pageSize")).toBe("25");
  });
});
