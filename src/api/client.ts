/**
 * Single HTTP boundary for the whole app.
 *
 * Today `USE_MOCK_ADAPTER` is true and every service resolves against the
 * in-memory adapter in `src/api/mock`. When the Django REST API is available,
 * flip VITE_API_MODE=live (or set VITE_API_URL) and only this file changes —
 * services, hooks and UI keep their contracts.
 */
export const API_BASE_URL = import.meta.env["VITE_API_URL"] ?? "/api";
export const USE_MOCK_ADAPTER = import.meta.env["VITE_API_MODE"] !== "live";
/** Auth/onboarding endpoints hit the real API even when VITE_API_MODE=mock. */
export const USE_LIVE_AUTH = import.meta.env["VITE_AUTH_LIVE"] === "true" || !USE_MOCK_ADAPTER;

export class ApiRequestError extends Error {
  status: number;
  code?: string | undefined;
  fieldErrors?: Record<string, string> | undefined;
  constructor(message: string, status = 500, code?: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

export const FRIENDLY_ERROR =
  "Something went wrong while loading this information. Please try again.";

let accessToken: string | null = null;
export function setAccessToken(token: string | null) {
  accessToken = token;
}

/**
 * Called once when an authenticated request comes back with HTTP 401, so the
 * session layer can drop the stored session and redirect to the login page
 * (spec §5 session expiration, §39 401 handling).
 */
let unauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const withSlash = path.endsWith("/") ? path : `${path}/`;
  const url = new URL(`${API_BASE_URL}${withSlash}`, globalThis.location?.origin ?? "http://localhost");
  Object.entries(options.query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  });

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: options.method ?? "GET",
      ...(options.signal ? { signal: options.signal } : {}),
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      credentials: "include",
    });
  } catch {
    throw new ApiRequestError(
      "You appear to be offline. We'll retry when your connection returns.",
      0,
      "offline",
    );
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
      message?: string;
      errors?: Record<string, string>;
    } | null;
    const error = new ApiRequestError(
      payload?.detail ?? payload?.message ?? FRIENDLY_ERROR,
      response.status,
      undefined,
      payload?.errors,
    );
    if (response.status === 401 && accessToken && unauthorizedHandler) {
      unauthorizedHandler();
    }
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Simulated latency for the development adapter so loading states are real. */
export function mockDelay<T>(value: T, ms = 420): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export interface Paginated<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
}
