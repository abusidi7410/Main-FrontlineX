import type { Announcement } from "@/types";

/**
 * Announcement board rules, kept pure so they can be tested without a DOM.
 *
 * The board is a public-facing surface: parents and students read it too, so
 * every decision about which rows appear and in what order lives here rather
 * than inside a component.
 */

export const AUDIENCE_OPTIONS = ["All", "Staff", "Parents", "Students"] as const;

export type AudienceOption = (typeof AUDIENCE_OPTIONS)[number];

/** Tidy the composer input before it is validated. */
export function normaliseAudience(input: unknown): string[] {
  const parts =
    typeof input === "string" ? input.split(",") : Array.isArray(input) ? input : [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of parts) {
    const label = String(raw ?? "").trim();
    if (!label || seen.has(label)) continue;
    seen.add(label);
    out.push(label);
  }
  return out;
}

/**
 * Trim an ISO timestamp to the minute, matching what the backend accepts.
 *
 * `datetime-local` inputs omit the seconds and timezone, so a value read back
 * out of one is not in the exact shape `new Date()` would produce. Normalising
 * before comparison keeps "is this expiry in the past?" from failing on a
 * formatting difference.
 */
export function toIsoMinute(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

export function isExpired(item: Announcement, now = new Date()): boolean {
  if (!item.expiresAt) return false;
  const parsed = new Date(item.expiresAt);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.getTime() <= now.getTime();
}

/**
 * Compose the default selection for a role.
 *
 * "All" is only ever one of several selections: `All` alongside `Parents` is
 * redundant, and submitting it would silently reach the whole school when the
 * author only meant the parents. Selecting `All` therefore clears the rest.
 */
export function defaultAudience(role: string): string[] {
  switch (role) {
    case "parent":
      return ["Parents"];
    case "student":
      return ["Students"];
    default:
      return ["All"];
  }
}

export function selectAudience(current: string[], option: AudienceOption): string[] {
  if (option === "All") return ["All"];
  const withoutAll = current.filter((a) => a !== "All");
  return withoutAll.includes(option)
    ? withoutAll.filter((a) => a !== option)
    : [...withoutAll, option];
}

/**
 * What the author is actually going to reach, so the UI can show it before
 * publishing. This is a preview only — the backend re-resolves the audience and
 * the client is never trusted to compute the recipient set.
 */
export function audiencePreview(audience: string[]): string {
  const selected = normaliseAudience(audience);
  if (selected.length === 0) return "nobody yet";
  if (selected.includes("All")) return "everyone in the school";
  const counts = selected.length;
  return counts === 1 ? "one audience" : `${counts} audiences`;
}

/** Pinned first, then newest first; expired rows are dropped. */
export function orderBoard(items: Announcement[], now = new Date()): Announcement[] {
  return items
    .filter((item) => !isExpired(item, now))
    .slice()
    .sort((a, b) => {
      if (a.isPinned !== b.isPinned) return a.isPinned ? -1 : 1;
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });
}
