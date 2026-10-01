/**
 * Single HTTP boundary for the whole app.
 *
 * Every request hits the live Django REST API at API_BASE_URL.
 */

/**
 * The backend mounts every app under `/api/v1` (see `backend/config/urls.py`).
 * This constant is the single source of truth for that prefix: services pass
 * relative paths such as `/students`, and the client joins them onto it. Do
 * not repeat the prefix inside individual services.
 */
export const API_PREFIX = "/api/v1";

/**
 * Strip trailing slashes so a misconfigured env var cannot produce `//`.
 *
 * A legacy `VITE_API_URL` ending in `/api` used to send every request to
 * un-versioned `/api/...` endpoints, which 404 against the versioned backend.
 * Rewrite that shape back to `API_PREFIX` so a stale env var cannot silently
 * reintroduce the mismatch this module exists to prevent.
 */
function normaliseBaseUrl(value: string): string {
  const trimmed = value.replace(/\/+$/, "");
  if (/\/api$/i.test(trimmed)) return `${trimmed}${API_PREFIX.slice("/api".length)}`;
  return trimmed;
}

export const API_BASE_URL = normaliseBaseUrl(import.meta.env["VITE_API_URL"] || API_PREFIX);

/** Exposed so tests can pin the legacy-`/api` rewrite. */
export const normaliseForTest = normaliseBaseUrl;

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
export function getAccessToken() {
  return accessToken;
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
  const url = new URL(
    `${API_BASE_URL}${withSlash}`,
    globalThis.location?.origin ?? "http://localhost",
  );
  Object.entries(options.query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  });

  const isMultipart = typeof FormData !== "undefined" && options.body instanceof FormData;
  const requestBody =
    options.body === undefined
      ? undefined
      : isMultipart
        ? (options.body as FormData)
        : JSON.stringify(options.body);
  const requestHeaders: Record<string, string> = {
    ...(isMultipart ? {} : { "Content-Type": "application/json" }),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: options.method ?? "GET",
      ...(options.signal ? { signal: options.signal } : {}),
      headers: requestHeaders,
      ...(requestBody === undefined ? {} : { body: requestBody }),
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
      fieldErrors?: Record<string, string>;
    } | null;
    const error = new ApiRequestError(
      payload?.detail ?? payload?.message ?? FRIENDLY_ERROR,
      response.status,
      undefined,
      payload?.fieldErrors ?? payload?.errors,
    );
    if (response.status === 401 && accessToken && unauthorizedHandler) {
      unauthorizedHandler();
    }
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface Paginated<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
}
