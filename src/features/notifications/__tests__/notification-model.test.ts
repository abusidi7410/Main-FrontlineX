import { describe, expect, it } from "vitest";

import {
  applyAllRead,
  applyRead,
  filterByType,
  notificationMeta,
  NOTIFICATION_META,
  NOTIFICATION_TYPES,
  relativeAge,
  targetFor,
  typeCounts,
  unreadCount,
} from "@/features/notifications/notification-model";
import type { AppNotification } from "@/types";

function note(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    type: "system",
    title: "Notice",
    body: "Body",
    createdAt: "2026-03-01T09:00:00Z",
    read: false,
    readAt: null,
    link: "",
    ...overrides,
  };
}

describe("notification types", () => {
  it("covers exactly the eight types README 32 specifies", () => {
    expect([...NOTIFICATION_TYPES].sort()).toEqual(
      [
        "ai",
        "announcement",
        "attendance",
        "payment",
        "result",
        "security",
        "subscription",
        "system",
      ].sort(),
    );
    for (const type of NOTIFICATION_TYPES) {
      expect(NOTIFICATION_META[type].label).toBeTruthy();
    }
  });

  it("falls back to the system tone for an unknown type rather than throwing", () => {
    // A row written by a newer server must not blank out a whole list.
    expect(notificationMeta("quantum_flux").label).toBe("System");
  });
});

describe("unread counting", () => {
  it("counts only unread rows", () => {
    expect(
      unreadCount([note({ id: "a" }), note({ id: "b", read: true }), note({ id: "c" })]),
    ).toBe(2);
  });

  it("counts unread per type for the filter chips", () => {
    const counts = typeCounts([
      note({ id: "a", type: "payment" }),
      note({ id: "b", type: "payment" }),
      note({ id: "c", type: "result", read: true }),
      note({ id: "d", type: "result" }),
    ]);
    expect(counts).toEqual({ payment: 2, result: 1 });
  });

  it("omits types with nothing unread rather than reporting zero", () => {
    expect(typeCounts([note({ type: "ai", read: true })])).toEqual({});
  });
});

describe("filterByType", () => {
  const feed = [
    note({ id: "a", type: "payment" }),
    note({ id: "b", type: "result" }),
    note({ id: "c", type: "payment" }),
  ];

  it("returns the whole feed for all", () => {
    expect(filterByType(feed, "all")).toHaveLength(3);
  });

  it("narrows to one type without reordering", () => {
    expect(filterByType(feed, "payment").map((n) => n.id)).toEqual(["a", "c"]);
  });
});

describe("targetFor", () => {
  it("follows a root-relative link", () => {
    expect(targetFor(note({ link: "/finance/invoices" }))).toBe("/finance/invoices");
  });

  it("returns null when there is nowhere to go", () => {
    expect(targetFor(note({ link: "" }))).toBeNull();
  });

  it("refuses to navigate off the app", () => {
    // `link` is written by the server but still arrives as data; a scheme or a
    // protocol-relative host must never become a navigation target.
    expect(targetFor(note({ link: "https://evil.example/steal" }))).toBeNull();
    expect(targetFor(note({ link: "//evil.example/steal" }))).toBeNull();
    expect(targetFor(note({ link: "javascript:alert(1)" }))).toBeNull();
  });
});

describe("relativeAge", () => {
  const now = new Date("2026-03-01T12:00:00Z");

  it("reads as a short elapsed time, then a date", () => {
    expect(relativeAge("2026-03-01T11:59:30Z", now)).toBe("Just now");
    expect(relativeAge("2026-03-01T11:45:00Z", now)).toBe("15m ago");
    expect(relativeAge("2026-03-01T09:00:00Z", now)).toBe("3h ago");
    expect(relativeAge("2026-02-26T12:00:00Z", now)).toBe("3d ago");
  });

  it("stops guessing after a week instead of inventing precision", () => {
    const old = relativeAge("2025-11-01T12:00:00Z", now);
    expect(old).not.toMatch(/ago/);
    expect(old).toBeTruthy();
  });

  it("degrades quietly on an unparseable timestamp", () => {
    expect(relativeAge("not-a-date", now)).toBe("");
  });
});

describe("optimistic read updates", () => {
  it("marks one row and leaves the rest alone", () => {
    const feed = [note({ id: "a" }), note({ id: "b" })];
    const next = applyRead(feed, "a", "2026-03-01T12:00:00Z");
    expect(next[0]).toMatchObject({ id: "a", read: true, readAt: "2026-03-01T12:00:00Z" });
    expect(next[1]).toMatchObject({ id: "b", read: false, readAt: null });
  });

  it("does not mutate the previous page's rows", () => {
    // The bell and the notification centre share a cache entry, so an in-place
    // mutation would leak between both views.
    const feed = [note({ id: "a" })];
    applyRead(feed, "a", "2026-03-01T12:00:00Z");
    expect(feed[0]?.read).toBe(false);
  });

  it("marks everything read while preserving already-read timestamps", () => {
    const stamp = "2026-03-01T10:00:00Z";
    const feed = [note({ id: "a", read: true, readAt: stamp }), note({ id: "b" })];
    const next = applyAllRead(feed, "2026-03-01T12:00:00Z");
    expect(next.every((n) => n.read)).toBe(true);
    expect(next[0]?.readAt).toBe(stamp);
    expect(next[1]?.readAt).toBe("2026-03-01T12:00:00Z");
  });
});
