import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { BellOff, CheckCheck, ExternalLink } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { dateTimeFmt } from "@/lib/format";
import { NotificationPreferencesPanel } from "@/features/notifications/notification-preferences-panel";
import {
  applyAllRead,
  applyRead,
  filterByType,
  notificationMeta,
  NOTIFICATION_TYPES,
  targetFor,
  typeCounts,
} from "@/features/notifications/notification-model";
import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/services/school.service";
import type { AppNotification, NotificationType } from "@/types";

export const Route = createFileRoute("/_app/notifications")({
  head: () => ({
    meta: [
      { title: "Notifications — Frontline Nexus" },
      {
        name: "description",
        content: "Everything the school has sent you: payments, results, attendance and notices.",
      },
      { property: "og:title", content: "Notifications — Frontline Nexus" },
      {
        property: "og:description",
        content: "Everything the school has sent you, in one place.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: NotificationsPage,
});

/**
 * The header bell and this page share one query key shape, so the badge in the
 * shell updates the moment anything is read here without a page reload.
 */
const PAGE_SIZE = 25;

function NotificationsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<NotificationType | "all">("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const query = useQuery({
    queryKey: ["notifications", { pageSize: PAGE_SIZE }],
    queryFn: () => getNotifications({ pageSize: PAGE_SIZE }),
    refetchInterval: 60_000,
  });

  const key = ["notifications", { pageSize: PAGE_SIZE }] as const;
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const markOne = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: (updated) => {
      queryClient.setQueryData(key, (old: typeof query.data) =>
        old
          ? {
              ...old,
              results: applyRead(old.results, updated.id, updated.readAt ?? ""),
              unread: Math.max(0, old.unread - 1),
            }
          : old,
      );
      void invalidate();
    },
    onError: () => toast.error("We couldn't update that notification. Please try again."),
  });

  const markAll = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      queryClient.setQueryData(key, (old: typeof query.data) =>
        old
          ? { ...old, results: applyAllRead(old.results, new Date().toISOString()), unread: 0 }
          : old,
      );
      toast.success("All notifications marked as read.");
      void invalidate();
    },
    onError: () => toast.error("We couldn't mark your notifications as read."),
  });

  function open(item: AppNotification) {
    if (!item.read) markOne.mutate(item.id);
    const target = targetFor(item);
    if (target) void navigate({ to: target });
  }

  const items = query.data?.results ?? [];
  const unread = query.data?.unread ?? 0;
  const counts = typeCounts(items);
  const visible = filterByType(items, filter).filter((n) => !unreadOnly || !n.read);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description="Everything the school has sent you, newest first."
        actions={
          <Button
            variant="outline"
            onClick={() => markAll.mutate()}
            disabled={unread === 0 || markAll.isPending}
          >
            <CheckCheck className="size-4" aria-hidden="true" />
            {markAll.isPending ? "Marking…" : "Mark all read"}
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-pressed={filter === "all" && !unreadOnly}
          onClick={() => {
            setFilter("all");
            setUnreadOnly(false);
          }}
          className={
            filter === "all" && !unreadOnly
              ? "min-h-11 rounded-full border border-primary bg-primary-soft px-4 font-medium text-primary"
              : "min-h-11 rounded-full border bg-surface px-4 font-medium hover:bg-muted"
          }
        >
          All
          {unread > 0 ? <span className="ml-2 text-sm">{unread}</span> : null}
        </button>
        {NOTIFICATION_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            aria-pressed={filter === type}
            onClick={() => setFilter(type)}
            className={
              filter === type
                ? "min-h-11 rounded-full border border-primary bg-primary-soft px-4 font-medium text-primary"
                : "min-h-11 rounded-full border bg-surface px-4 font-medium hover:bg-muted"
            }
          >
            {notificationMeta(type).label}
            {counts[type] ? <span className="ml-2 text-sm">{counts[type]}</span> : null}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={unreadOnly}
          onClick={() => setUnreadOnly((v) => !v)}
          className={
            unreadOnly
              ? "ml-auto min-h-11 rounded-full border border-primary bg-primary-soft px-4 font-medium text-primary"
              : "ml-auto min-h-11 rounded-full border bg-surface px-4 font-medium hover:bg-muted"
          }
        >
          Unread only
        </button>
      </div>

      {query.isError ? (
        <ErrorState
          onRetry={() => void query.refetch()}
          message="We couldn't load your notifications. Please check your connection and try again."
        />
      ) : query.isPending ? (
        <ListSkeleton rows={6} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<BellOff className="size-6" aria-hidden="true" />}
          title="No notifications yet"
          description="When the school sends you a payment update, a result, or a notice, it will appear here."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description={
            unreadOnly
              ? "You have no unread notifications of this type. Try another filter."
              : "There are no notifications of this type."
          }
        />
      ) : (
        <ul className="fn-panel divide-y">
          {visible.map((item) => {
            const meta = notificationMeta(item.type);
            const hasLink = targetFor(item) !== null;
            return (
              <li key={item.id} className={item.read ? undefined : "bg-primary-soft/30"}>
                <div className="flex gap-3 p-5">
                  <span
                    aria-hidden="true"
                    className={`mt-2 size-2.5 shrink-0 rounded-full ${item.read ? "bg-border" : "bg-primary"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <p className={item.read ? "font-medium" : "font-semibold"}>{item.title}</p>
                      <p className="text-sm text-muted-foreground">
                        {dateTimeFmt(item.createdAt)}
                      </p>
                    </div>
                    {item.body ? <p className="mt-1 text-muted-foreground">{item.body}</p> : null}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-muted px-2.5 py-1 text-xs">
                        {meta.label}
                      </span>
                      {!item.read ? (
                        <span className="text-xs font-medium text-primary">Unread</span>
                      ) : null}
                      <span className="ml-auto flex gap-2">
                        {!item.read ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => markOne.mutate(item.id)}
                            disabled={markOne.isPending}
                          >
                            Mark read
                          </Button>
                        ) : null}
                        {hasLink ? (
                          <Button variant="outline" size="sm" onClick={() => open(item)}>
                            Open
                            <ExternalLink className="size-4" aria-hidden="true" />
                          </Button>
                        ) : null}
                      </span>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <section aria-labelledby="notification-preferences-heading" className="space-y-2 pt-2">
        <h2 id="notification-preferences-heading" className="text-lg font-semibold">
          What reaches you
        </h2>
        <p className="text-sm text-muted-foreground">
          These are your own settings, and apply whichever role or school you sign in with.
        </p>
        <NotificationPreferencesPanel compact />
      </section>
    </div>
  );
}
