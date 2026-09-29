import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL, API_PREFIX, apiFetch, setAccessToken } from "../client";
import {
  listStudents,
  createStudent,
  transferStudent,
  updateStudent,
} from "@/services/students.service";
import { listStaff } from "@/services/staff.service";
import { getSubscription } from "@/services/school.service";
import { getRoster, submitAttendance } from "@/services/attendance.service";
import { login } from "@/services/auth.service";

/**
 * Phase 1: the backend mounts every app under `/api/v1`, and the frontend must
 * reach it through exactly one centralized prefix.
 *
 * These tests fail if a service hardcodes `/api` (or any other prefix) instead
 * of passing a relative path, which is how the original mismatch happened.
 */

function mockOk() {
  // A fresh Response per call: reusing one throws "Body has already been read".
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify({ ok: true, results: [], count: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestedPaths(fetchMock: ReturnType<typeof mockOk>): string[] {
  return fetchMock.mock.calls.map(([url]) => new URL(url as string).pathname);
}

afterEach(() => {
  setAccessToken(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API prefix", () => {
  it("exposes /api/v1 as the single source of truth", () => {
    expect(API_PREFIX).toBe("/api/v1");
  });

  it("never yields a base URL below the /api/v1 prefix", () => {
    // Whichever env value is active, the effective base must stay versioned.
    // This is the assertion that would have caught the original bug.
    expect(API_BASE_URL.endsWith(API_PREFIX)).toBe(true);
    expect(API_BASE_URL).not.toMatch(/\/api$/i);
  });

  it("never produces a double slash when joining", async () => {
    const fetchMock = mockOk();
    await apiFetch("/students");
    expect(requestedPaths(fetchMock)[0]).toBe("/api/v1/students/");
  });

  it("upgrades a legacy '/api' env value to '/api/v1'", async () => {
    const { normaliseForTest } = await import("../client");
    // A stale VITE_API_URL must not reintroduce un-versioned routes.
    expect(normaliseForTest("http://localhost:8000/api")).toBe("http://localhost:8000/api/v1");
    expect(normaliseForTest("http://localhost:8000/api/")).toBe("http://localhost:8000/api/v1");
    expect(normaliseForTest("http://localhost:8000/api/v1")).toBe("http://localhost:8000/api/v1");
    expect(normaliseForTest("http://localhost:8000/api/v2")).toBe("http://localhost:8000/api/v2");
    expect(normaliseForTest("")).toBe("");
  });
});

describe("services route through the centralized /api/v1 prefix", () => {
  it("covers students, staff, school, attendance, transfer and auth", async () => {
    const fetchMock = mockOk();

    await listStudents();
    await listStaff();
    await getSubscription();
    await getRoster({ className: "JSS 1" });
    await submitAttendance({
      id: "roster-1",
      className: "JSS 1",
      date: "2026-09-20",
      records: [],
      syncState: "synced",
      updatedAt: 1758345600000,
    });
    await login("a@b.c", "x");
    await createStudent({
      firstName: "Ada",
      lastName: "Nwosu",
      admissionNumber: "SUA/JSS/2026/000001",
      gender: "female",
      dateOfBirth: "2014-05-02",
      className: "JSS 1",
      arm: "A",
      guardianName: "Mrs N",
      guardianPhone: "+234",
    });
    await updateStudent("abc", {
      firstName: "Ada",
      lastName: "Nwosu",
      admissionNumber: "SUA/JSS/2026/000001",
      gender: "female",
      dateOfBirth: "2014-05-02",
      className: "JSS 1",
      arm: "A",
      guardianName: "Mrs N",
      guardianPhone: "+234",
    });
    await transferStudent({ studentId: "abc", toSchoolId: "2" });

    for (const path of requestedPaths(fetchMock)) {
      // Every request must carry the versioned prefix...
      expect(path.startsWith("/api/v1/")).toBe(true);
      // ...and must NOT be a bare un-versioned `/api/...` path, which is the
      // exact shape of the original bug. `/api/v1/...` legitimately also
      // starts with `/api/`, so check the segment after the prefix.
      expect(
        path === "/api/" || path.startsWith("/api/auth/") || path.startsWith("/api/students/"),
      ).toBe(false);
    }
  });

  it("builds the expected concrete routes", async () => {
    const fetchMock = mockOk();
    await listStudents();
    await getRoster({ className: "JSS 1" });
    await transferStudent({ studentId: "abc", toSchoolId: "2" });

    const paths = requestedPaths(fetchMock);
    expect(paths).toContain("/api/v1/students/");
    expect(paths).toContain("/api/v1/attendance/roster/");
    expect(paths).toContain("/api/v1/students/abc/transfer/");
  });

  it("sends the bearer token so the backend can scope by school", async () => {
    const fetchMock = mockOk();
    setAccessToken("token-123");
    await listStudents();
    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(request.headers).get("Authorization")).toBe("Bearer token-123");
  });
});
