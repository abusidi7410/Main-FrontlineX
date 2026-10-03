import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/api/client";
import {
  createAnnouncement,
  deleteAnnouncement,
  getAnnouncements,
  getNotificationPreferences,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  saveNotificationPreferences,
  updateAnnouncement,
} from "@/services/school.service";
import type { Announcement, AppNotification, NotificationPage } from "@/types";

/**
 * Two contract risks live in these service functions, and neither shows up in a
 * screenshot:
 *
 *  1. `getNotifications` used to return a bare array and now returns a page
 *     envelope with the unread total riding along. If a caller is built against
 *     the wrong shape it will fail at runtime, not at build time.
 *  2. Query parameters are built by hand, so an unset filter must be *absent*
 *     rather than sent as an empty string, which the backend would reject.
 */
vi.mock("@/api/client", () => ({ apiFetch: vi.fn() }));

const notice: AppNotification = {
  id: "9",
  type: "payment",
  title: "Payment received",
  body: "₦20,000 received for JSS 1.",
  createdAt: "2026-03-01T09:00:00Z",
  read: false,
  readAt: null,
  link: "/finance/invoices",
};

const page: NotificationPage = {
  results: [notice],
  count: 1,
  page: 1,
  pageSize: 25,
  hasMore: false,
  unread: 3,
};

const announcement: Announcement = {
  id: "4",
  title: "Closed for elections",
  body: "The school will be closed on Friday.",
  audience: ["Parents"],
  createdAt: "2026-03-01T09:00:00Z",
  author: "Head Teacher",
  isPinned: true,
  expiresAt: null,
  scope: "school",
};

describe("getNotifications", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("returns the page envelope with the unread total intact", async () => {
    vi.mocked(apiFetch).mockResolvedValue(page);
    const result = await getNotifications();
    // The unread count covers the whole feed, not just this page, so it must
    // survive as the server's own number rather than being recomputed.
    expect(result.unread).toBe(3);
    expect(result.results[0]?.link).toBe("/finance/invoices");
    expect(apiFetch).toHaveBeenCalledWith("/notifications", { query: {} });
  });

  it("omits every filter that was not asked for", async () => {
    vi.mocked(apiFetch).mockResolvedValue(page);
    await getNotifications();
    const [, options] = vi.mocked(apiFetch).mock.calls[0] as [string, { query: Record<string, string> }];
    expect(Object.keys(options.query)).toHaveLength(0);
  });

  it("sends the unread and type filters it was given", async () => {
    vi.mocked(apiFetch).mockResolvedValue(page);
    await getNotifications({ unreadOnly: true, type: "payment", page: 2, pageSize: 25 });
    expect(apiFetch).toHaveBeenCalledWith("/notifications", {
      query: { unread: "true", type: "payment", page: "2", pageSize: "25" },
    });
  });

  it("does not send unread=false, which is not the same as omitting it", async () => {
    vi.mocked(apiFetch).mockResolvedValue(page);
    await getNotifications({ unreadOnly: false });
    const [, options] = vi.mocked(apiFetch).mock.calls[0] as [string, { query: Record<string, string> }];
    expect(options.query).not.toHaveProperty("unread");
  });
});

describe("read receipts", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("marks one notification read at its own endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...notice, read: true });
    const result = await markNotificationRead("9");
    expect(apiFetch).toHaveBeenCalledWith("/notifications/9/read", { method: "POST" });
    expect(result.read).toBe(true);
  });

  it("marks everything read through the bulk endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ markedRead: 3 });
    const result = await markAllNotificationsRead();
    expect(apiFetch).toHaveBeenCalledWith("/notifications/read-all", { method: "POST" });
    expect(result.markedRead).toBe(3);
  });
});

describe("notification preferences", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("reads preferences from the self-service endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue([{ type: "payment", label: "Payments", inApp: true }]);
    await getNotificationPreferences();
    expect(apiFetch).toHaveBeenCalledWith("/notifications/preferences");
  });

  it("sends only the fields the backend persists", async () => {
    vi.mocked(apiFetch).mockResolvedValue([]);
    await saveNotificationPreferences([{ type: "payment", inApp: false }]);
    expect(apiFetch).toHaveBeenCalledWith("/notifications/preferences", {
      method: "PATCH",
      body: { preferences: [{ type: "payment", inApp: false }] },
    });
  });
});

describe("announcements", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("reads the audience-filtered board without filtering again on the client", async () => {
    vi.mocked(apiFetch).mockResolvedValue([announcement]);
    const result = await getAnnouncements();
    expect(apiFetch).toHaveBeenCalledWith("/announcements");
    expect(result[0]?.audience).toEqual(["Parents"]);
    expect(result[0]?.isPinned).toBe(true);
  });

  it("creates with the pin and expiry the composer now sends", async () => {
    vi.mocked(apiFetch).mockResolvedValue(announcement);
    await createAnnouncement({
      title: "Closed for elections",
      body: "The school will be closed on Friday.",
      audience: ["Parents"],
      isPinned: false,
      expiresAt: null,
    });
    expect(apiFetch).toHaveBeenCalledWith("/announcements", {
      method: "POST",
      body: {
        title: "Closed for elections",
        body: "The school will be closed on Friday.",
        audience: ["Parents"],
        isPinned: false,
        expiresAt: null,
      },
    });
  });

  it("patches only the pin flag when pinning", async () => {
    vi.mocked(apiFetch).mockResolvedValue(announcement);
    await updateAnnouncement("4", { isPinned: true });
    expect(apiFetch).toHaveBeenCalledWith("/announcements/4", {
      method: "PATCH",
      body: { isPinned: true },
    });
  });

  it("clears an expiry with an explicit null rather than omitting it", async () => {
    vi.mocked(apiFetch).mockResolvedValue(announcement);
    await updateAnnouncement("4", { expiresAt: null });
    const [, options] = vi.mocked(apiFetch).mock.calls[0] as [
      string,
      { body: Record<string, unknown> },
    ];
    expect(options.body).toHaveProperty("expiresAt", null);
  });

  it("deletes by id", async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined);
    await deleteAnnouncement("4");
    expect(apiFetch).toHaveBeenCalledWith("/announcements/4", { method: "DELETE" });
  });
});
