import type { AppNotification, NotificationType } from "@/types";

/**
 * Notification presentation and feed rules, kept out of the components so it
 * can be tested without a DOM and so the header bell and the notification
 * centre can never drift into showing the same feed differently.
 *
 * The eight types are README 32's list. Each carries its own label and tone
 * because "Result" and "Payment" are not interchangeable to somebody deciding
 * whether to open something.
 */

export interface NotificationMeta {
  label: string;
  /** Short form for the header badge and dense rows. */
  short: string;
  /** Drives the accent dot and the row border. */
  tone: "brand" | "positive" | "warning" | "critical" | "muted";
}

/**
 * README 32's eight types, in the order a reader cares about them: money,
 * marks, presence, then the school's own voice, then account-level matters.
 */
export const NOTIFICATION_TYPES: readonly NotificationType[] = [
  "payment",
  "result",
  "attendance",
  "announcement",
  "subscription",
  "security",
  "ai",
  "system",
];

export const NOTIFICATION_META: Record<NotificationType, NotificationMeta> = {
  payment: { label: "Payments", short: "Pay", tone: "positive" },
  attendance: { label: "Attendance", short: "Att", tone: "warning" },
  result: { label: "Results", short: "Res", tone: "brand" },
  announcement: { label: "Announcements", short: "Ann", tone: "brand" },
  subscription: { label: "Subscription", short: "Sub", tone: "critical" },
  ai: { label: "AI usage", short: "AI", tone: "muted" },
  security: { label: "Security", short: "Sec", tone: "critical" },
  system: { label: "System", short: "Sys", tone: "muted" },
};

export function notificationMeta(type: string): NotificationMeta {
  return NOTIFICATION_META[type as NotificationType] ?? NOTIFICATION_META.system;
}

export function unreadCount(notifications: AppNotification[]): number {
  return notifications.filter((n) => !n.read).length;
}

/** How many unread of each type are in this page, for the filter chips. */
export function typeCounts(notifications: AppNotification[]): Partial<Record<NotificationType, number>> {
  const counts: Partial<Record<NotificationType, number>> = {};
  for (const item of notifications) {
    if (item.read) continue;
    counts[item.type] = (counts[item.type] ?? 0) + 1;
  }
  return counts;
}

export function filterByType(
  notifications: AppNotification[],
  type: NotificationType | "all",
): AppNotification[] {
  if (type === "all") return notifications;
  return notifications.filter((n) => n.type === type);
}

/**
 * Where a notification should take the reader.
 *
 * `link` is a server-supplied in-app path. It is treated as a hint rather than
 * trusted blindly: only a root-relative path is followed, so a stored value can
 * never navigate the reader off the app.
 */
export function targetFor(item: AppNotification): string | null {
  if (!item.link) return null;
  if (!item.link.startsWith("/") || item.link.startsWith("//")) return null;
  return item.link;
}

/**
 * A short relative description used where a full timestamp will not fit.
 *
 * Deliberately coarse: "Just now" through days, then a date. Exact clock times
 * are handled by the shared date formatter on the wider layouts.
 */
export function relativeAge(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return then.toLocaleDateString();
}

/** Mark one item read locally so the list does not wait for a refetch. */
export function applyRead(
  notifications: AppNotification[],
  id: string,
  readAt: string,
): AppNotification[] {
  return notifications.map((n) => (n.id === id ? { ...n, read: true, readAt } : n));
}

/** Mark everything read locally, keeping the server's ordering. */
export function applyAllRead(
  notifications: AppNotification[],
  readAt: string,
): AppNotification[] {
  return notifications.map((n) => (n.read ? n : { ...n, read: true, readAt }));
}
