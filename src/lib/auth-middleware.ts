import { API_BASE_URL, getAccessToken } from "@/api/client";
import { createMiddleware } from "@tanstack/react-start";
import { setResponseStatus } from "@tanstack/react-start/server";
import type { AuthUser, Permission, Role } from "@/types";

export interface ServerPrincipal {
  user: Pick<AuthUser, "id" | "role" | "permissions" | "schoolId">;
}

export interface AuthorizationFailure {
  statusCode: number;
  code: string;
  message: string;
}

const roles = new Set<Role>([
  "platform_manager",
  "school_admin",
  "principal",
  "teacher",
  "accountant",
  "secretary",
  "parent",
  "student",
]);

export class ServerAuthorizationError extends Error {
  readonly statusCode: number;
  readonly code: string;

  constructor(statusCode: number, code: string, message: string) {
    super(message);
    this.name = "ServerAuthorizationError";
    this.statusCode = statusCode;
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRole(value: unknown): value is Role {
  return typeof value === "string" && roles.has(value as Role);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function parseServerPrincipal(payload: unknown): ServerPrincipal {
  const userPayload = isRecord(payload) ? payload["user"] : undefined;
  if (!isRecord(userPayload)) {
    throw new TypeError("Authentication response does not contain a user.");
  }

  const id = userPayload["id"];
  const role = userPayload["role"];
  const permissions = userPayload["permissions"];
  const schoolId = userPayload["schoolId"];
  if (
    !isNonEmptyString(id) ||
    !isRole(role) ||
    !Array.isArray(permissions) ||
    !permissions.every(isNonEmptyString) ||
    !(schoolId === null || isNonEmptyString(schoolId))
  ) {
    throw new TypeError("Authentication response contains an invalid user.");
  }

  return {
    user: {
      id,
      role,
      permissions: permissions as Permission[],
      schoolId,
    },
  };
}

export function getPermissionFailure(
  principal: ServerPrincipal,
  permission: Permission,
): AuthorizationFailure | null {
  if (principal.user.permissions.includes(permission)) return null;
  return {
    statusCode: 403,
    code: "PERMISSION_DENIED",
    message: "Permission denied.",
  };
}

export function getSchoolScopeFailure(
  principal: ServerPrincipal,
  resourceSchoolId: string,
): AuthorizationFailure | null {
  if (principal.user.schoolId && principal.user.schoolId === resourceSchoolId) return null;
  return {
    statusCode: 404,
    code: "RESOURCE_NOT_FOUND",
    message: "Resource not found.",
  };
}

function reject(failure: AuthorizationFailure): never {
  setResponseStatus(failure.statusCode);
  throw new ServerAuthorizationError(failure.statusCode, failure.code, failure.message);
}

export function assertSameSchool(principal: ServerPrincipal, resourceSchoolId: string): void {
  const failure = getSchoolScopeFailure(principal, resourceSchoolId);
  if (failure) reject(failure);
}

function getAuthUrl(request: Request): URL {
  // Reuse the single API boundary so server-side auth checks cannot drift onto
  // an un-versioned `/api` path, which 404s against the versioned backend.
  return new URL(`${API_BASE_URL}/auth/me/`, request.url);
}

const accessTokenMiddleware = createMiddleware({ type: "function" }).client(({ next }) => {
  const token = getAccessToken();
  return next(token ? { headers: { Authorization: `Bearer ${token}` } } : undefined);
});

const authenticateMiddleware = createMiddleware().server(async ({ request, next }) => {
  const authorization = request.headers.get("authorization");
  const token = authorization?.match(/^Bearer ([^\s]+)$/)?.[1];
  if (!token) {
    reject({
      statusCode: 401,
      code: "AUTHENTICATION_REQUIRED",
      message: "Authentication required.",
    });
  }

  try {
    const response = await fetch(getAuthUrl(request), {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      signal: request.signal,
    });

    if (response.status === 401) {
      reject({
        statusCode: 401,
        code: "AUTHENTICATION_REQUIRED",
        message: "Authentication required.",
      });
    }
    if (response.status === 403) {
      reject({
        statusCode: 403,
        code: "ACCOUNT_ACCESS_DENIED",
        message: "Account access denied.",
      });
    }
    if (!response.ok) {
      reject({
        statusCode: 502,
        code: "AUTH_SERVICE_UNAVAILABLE",
        message: "Authentication service unavailable.",
      });
    }

    const principal = parseServerPrincipal(await response.json());
    return next({ context: { principal } });
  } catch (error) {
    if (error instanceof ServerAuthorizationError) throw error;
    reject({
      statusCode: 502,
      code: "AUTH_SERVICE_UNAVAILABLE",
      message: "Authentication service unavailable.",
    });
  }
});

export function requirePermission(permission: Permission) {
  return createMiddleware({ type: "function" })
    .middleware([accessTokenMiddleware, authenticateMiddleware])
    .server(({ context, next }) => {
      const failure = getPermissionFailure(context.principal, permission);
      if (failure) reject(failure);
      return next();
    });
}

export function requireSameSchool() {
  return createMiddleware({ type: "function" })
    .middleware([accessTokenMiddleware, authenticateMiddleware])
    .server(({ context, data, next }) => {
      const schoolId = isRecord(data) ? data["schoolId"] : undefined;
      if (!isNonEmptyString(schoolId)) {
        reject({
          statusCode: 400,
          code: "SCHOOL_ID_REQUIRED",
          message: "A valid schoolId is required.",
        });
      }

      const failure = getSchoolScopeFailure(context.principal, schoolId);
      if (failure) reject(failure);
      return next();
    });
}
