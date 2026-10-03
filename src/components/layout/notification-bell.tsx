import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Bell, CheckCheck, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  applyAllRead,
  applyRead,
  notificationMeta,
  relativeAge,
  targetFor,
  unreadCount,
} from "@/features/notifications/notification-model";
import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/services/school.service";

/**
 * How often the badge refreshes.
 *
 * Polling rather than a socket: there is no realtime channel in this stack, and
 * the feed is read-only and low-volume, so a one-minute poll is enough to keep
 * the badge honest without holding a connection open on every open tab. The
 * query is shared with the notification centre, so this costs one request per
 * minute regardless of how many components show it.
 */
const REFRESH_MS = 60_000;

export function NotificationBell() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data, isPending, isError } = useQuery({
    queryKey: ["notifications", { pageSize: 8 }],
    queryFn: () => getNotifications({ pageSize: 8 }),
    refetchInterval: REFRESH_MS,
  });

  const items = data?.results ?? [];
  // The server's unread total covers the whole feed; counting the loaded page
  // would understate the badge whenever the unread items are not all on page 1.
  const unread = data?.unread ?? unreadCount(items);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const markOne = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: (updated) => {
      queryClient.setQueryData(
        ["notifications", { pageSize: 8 }],
        (old: typeof data) =>
          old ? { ...old, results: applyRead(old.results, updated.id, updated.readAt ?? "") } : old,
      );
      void invalidate();
    },
  });

  const markAll = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      queryClient.setQueryData(
        ["notifications", { pageSize: 8 }],
        (old: typeof data) =>
          old
            ? { ...old, results: applyAllRead(old.results, new Date().toISOString()), unread: 0 }
            : old,
      );
      void invalidate();
    },
  });

  function open(item: (typeof items)[number]) {
    if (!item.read) markOne.mutate(item.id);
    const target = targetFor(item);
    if (target) void navigate({ to: target });
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="relative size-10"
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell className="size-5" aria-hidden="true" />
          {unread > 0 ? (
            <span className="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-xs font-semibold text-destructive-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(92vw,22rem)] p-0">
        <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
          <p className="font-semibold">
            Notifications
            {unread > 0 ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">{unread} unread</span>
            ) : null}
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => markAll.mutate()}
            disabled={unread === 0 || markAll.isPending}
          >
            <CheckCheck className="size-4" aria-hidden="true" />
            Mark all read
          </Button>
        </div>

        <ScrollArea className="max-h-80">
          {isPending ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Loading notifications…</p>
          ) : isError ? (
            <div className="px-4 py-6 text-sm">
              <p className="font-medium">We couldn't load your notifications.</p>
              <p className="mt-1 text-muted-foreground">
                Check your connection and try again.
              </p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => void invalidate()}>
                Retry
              </Button>
            </div>
          ) : items.length > 0 ? (
            <ul className="divide-y">
              {items.map((item) => {
                const meta = notificationMeta(item.type);
                const hasLink = targetFor(item) !== null;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => open(item)}
                      className="flex w-full gap-3 px-4 py-3 text-left hover:bg-muted/60"
                    >
                      <span
                        aria-hidden="true"
                        className={`mt-1.5 size-2 shrink-0 rounded-full ${
                          item.read ? "bg-border" : "bg-primary"
                        }`}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline justify-between gap-2">
                          <span className={`text-sm ${item.read ? "font-medium" : "font-semibold"}`}>
                            {item.title}
                          </span>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {relativeAge(item.createdAt)}
                          </span>
                        </span>
                        {item.body ? (
                          <span className="mt-0.5 block text-sm text-muted-foreground">
                            {item.body}
                          </span>
                        ) : null}
                        <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <span className="rounded-full bg-muted px-2 py-0.5">{meta.label}</span>
                          {hasLink ? (
                            <span className="inline-flex items-center gap-1">
                              Open
                              <ExternalLink className="size-3" aria-hidden="true" />
                            </span>
                          ) : null}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              You have no notifications yet.
            </p>
          )}
        </ScrollArea>

        {items.length > 0 ? (
          <div className="border-t px-2 py-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => void navigate({ to: "/notifications" })}
            >
              View all notifications
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
