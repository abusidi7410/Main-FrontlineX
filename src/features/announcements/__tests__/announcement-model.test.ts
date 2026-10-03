import { describe, expect, it } from "vitest";

import {
  audiencePreview,
  defaultAudience,
  isExpired,
  normaliseAudience,
  orderBoard,
  selectAudience,
  toIsoMinute,
} from "@/features/announcements/announcement-model";
import type { Announcement } from "@/types";

function notice(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    title: "Notice",
    body: "Body",
    audience: ["All"],
    createdAt: "2026-03-01T09:00:00Z",
    author: "Head Teacher",
    isPinned: false,
    expiresAt: null,
    scope: "school",
    ...overrides,
  };
}

describe("normaliseAudience", () => {
  it("keeps the composer labels the backend accepts", () => {
    expect(normaliseAudience(["Parents", "Students"])).toEqual(["Parents", "Students"]);
  });

  it("trims, drops blanks and removes duplicates", () => {
    expect(normaliseAudience([" Parents ", "", "Parents", null])).toEqual(["Parents"]);
  });

  it("accepts a comma-separated string from a pasted value", () => {
    expect(normaliseAudience("Staff, Parents ,Staff")).toEqual(["Staff", "Parents"]);
  });

  it("returns nothing usable rather than throwing on junk", () => {
    expect(normaliseAudience(undefined)).toEqual([]);
    expect(normaliseAudience(42)).toEqual([]);
  });
});

describe("defaultAudience", () => {
  it("defaults a family member to their own side", () => {
    // "All" reaches the entire school, so it must never be the default for
    // somebody who is only ever here about their own children.
    expect(defaultAudience("parent")).toEqual(["Parents"]);
    expect(defaultAudience("student")).toEqual(["Students"]);
  });

  it("defaults staff to the whole school", () => {
    expect(defaultAudience("school_admin")).toEqual(["All"]);
    expect(defaultAudience("principal")).toEqual(["All"]);
  });
});

describe("selectAudience", () => {
  it("makes All exclusive, because All plus Parents is just All", () => {
    expect(selectAudience(["Parents", "Students"], "All")).toEqual(["All"]);
  });

  it("clears All when a narrower audience is added", () => {
    expect(selectAudience(["All"], "Staff")).toEqual(["Staff"]);
  });

  it("toggles a specific audience off", () => {
    expect(selectAudience(["Staff", "Parents"], "Staff")).toEqual(["Parents"]);
  });

  it("adds a specific audience alongside another", () => {
    expect(selectAudience(["Staff"], "Parents")).toEqual(["Staff", "Parents"]);
  });
});

describe("audiencePreview", () => {
  it("says plainly what a wide selection reaches", () => {
    expect(audiencePreview(["All"])).toBe("everyone in the school");
    expect(audiencePreview(["Parents"])).toBe("one audience");
    expect(audiencePreview(["Parents", "Students"])).toBe("2 audiences");
  });

  it("warns about the empty case instead of implying school-wide", () => {
    expect(audiencePreview([])).toBe("nobody yet");
  });
});

describe("toIsoMinute", () => {
  it("returns a full ISO timestamp the backend can parse", () => {
    // `datetime-local` gives local wall-clock time with no zone, so the
    // conversion has to be to UTC to match what the backend stores.
    expect(toIsoMinute("2026-03-01T09:30")).toBe(new Date("2026-03-01T09:30").toISOString());
  });

  it("treats an empty field as no expiry rather than an error", () => {
    expect(toIsoMinute("")).toBeNull();
    expect(toIsoMinute("   ")).toBeNull();
  });

  it("returns null on an unparseable value instead of sending Invalid Date", () => {
    expect(toIsoMinute("next tuesday-ish")).toBeNull();
  });
});

describe("isExpired", () => {
  const now = new Date("2026-03-01T12:00:00Z");

  it("never expires a notice with no expiry", () => {
    expect(isExpired(notice({ expiresAt: null }), now)).toBe(false);
  });

  it("expires once the moment has passed", () => {
    expect(isExpired(notice({ expiresAt: "2026-03-01T11:59:00Z" }), now)).toBe(true);
  });

  it("keeps a notice alive right up to its expiry", () => {
    expect(isExpired(notice({ expiresAt: "2026-03-01T12:00:00Z" }), now)).toBe(true);
    expect(isExpired(notice({ expiresAt: "2026-03-01T12:00:01Z" }), now)).toBe(false);
  });
});

describe("orderBoard", () => {
  const now = new Date("2026-03-01T12:00:00Z");

  it("puts pinned notices above everything else", () => {
    const board = orderBoard(
      [
        notice({ id: "newest", createdAt: "2026-03-01T11:00:00Z" }),
        notice({ id: "pinned-old", createdAt: "2026-01-01T09:00:00Z", isPinned: true }),
      ],
      now,
    );
    expect(board.map((n) => n.id)).toEqual(["pinned-old", "newest"]);
  });

  it("orders the rest newest first", () => {
    const board = orderBoard(
      [
        notice({ id: "old", createdAt: "2026-02-01T09:00:00Z" }),
        notice({ id: "new", createdAt: "2026-03-01T11:00:00Z" }),
        notice({ id: "mid", createdAt: "2026-02-15T09:00:00Z" }),
      ],
      now,
    );
    expect(board.map((n) => n.id)).toEqual(["new", "mid", "old"]);
  });

  it("drops an expired notice instead of showing a stale one", () => {
    const board = orderBoard(
      [
        notice({ id: "live" }),
        notice({ id: "gone", expiresAt: "2026-02-01T00:00:00Z" }),
      ],
      now,
    );
    expect(board.map((n) => n.id)).toEqual(["live"]);
  });

  it("does not mutate the array it was given", () => {
    // The query cache holds this array; sorting in place would reorder whatever
    // else is reading it.
    const input = [
      notice({ id: "old", createdAt: "2026-01-01T09:00:00Z" }),
      notice({ id: "new", createdAt: "2026-03-01T11:00:00Z" }),
    ];
    orderBoard(input, now);
    expect(input.map((n) => n.id)).toEqual(["old", "new"]);
  });
});
