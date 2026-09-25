import { describe, expect, it } from "vitest";

import {
  getPermissionFailure,
  getSchoolScopeFailure,
  parseServerPrincipal,
  type ServerPrincipal,
} from "../auth-middleware";

function principal(overrides: Partial<ServerPrincipal["user"]> = {}): ServerPrincipal {
  return {
    user: {
      id: "user-1",
      role: "school_admin",
      permissions: ["students.read", "students.write"],
      schoolId: "school-1",
      ...overrides,
    },
  };
}

describe("server authorization", () => {
  it("parses a trusted backend principal", () => {
    expect(
      parseServerPrincipal({
        user: {
          id: "user-1",
          role: "principal",
          permissions: ["students.read"],
          schoolId: "school-1",
        },
      }),
    ).toEqual(principal({ role: "principal", permissions: ["students.read"] }));
  });

  it("rejects malformed authentication payloads", () => {
    expect(() =>
      parseServerPrincipal({
        user: {
          id: "user-1",
          role: "unknown-role",
          permissions: ["students.read"],
          schoolId: "school-1",
        },
      }),
    ).toThrow(TypeError);
    expect(() =>
      parseServerPrincipal({
        user: {
          id: "user-1",
          role: "teacher",
          permissions: [42],
          schoolId: "school-1",
        },
      }),
    ).toThrow(TypeError);
  });

  it("allows only permissions granted by the backend principal", () => {
    expect(getPermissionFailure(principal(), "students.read")).toBeNull();
    expect(getPermissionFailure(principal(), "finance.write")).toEqual({
      statusCode: 403,
      code: "PERMISSION_DENIED",
      message: "Permission denied.",
    });
  });

  it("allows only resources in the authenticated school", () => {
    expect(getSchoolScopeFailure(principal(), "school-1")).toBeNull();
    expect(getSchoolScopeFailure(principal(), "school-2")).toEqual({
      statusCode: 404,
      code: "RESOURCE_NOT_FOUND",
      message: "Resource not found.",
    });
  });

  it("does not grant tenant scope to platform managers", () => {
    expect(
      getSchoolScopeFailure(
        principal({ role: "platform_manager", permissions: ["platform.manage"], schoolId: null }),
        "school-1",
      ),
    ).toEqual({
      statusCode: 404,
      code: "RESOURCE_NOT_FOUND",
      message: "Resource not found.",
    });
  });
});
