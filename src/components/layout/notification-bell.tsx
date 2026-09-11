import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getNotifications, markAllNotificationsRead } from "@/services/school.service";
import { dateTimeFmt } from "@/lib/format";

export function NotificationBell() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ["notifications"], queryFn: getNotifications });
  const markRead = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unread = data?.filter((n) => !n.read).length ?? 0;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="relative size-10"
          aria-label={`Notifications, ${unread} unread`}
        >
          <Bell className="size-5" aria-hidden="true" />
          {unread > 0 ? (
            <span className="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-xs font-semibold text-destructive-foreground">
              {unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(92vw,22rem)] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="font-semibold">Notifications</p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => markRead.mutate()}
            disabled={unread === 0 || markRead.isPending}
          >
            Mark all read
          </Button>
        </div>
        <ScrollArea className="max-h-80">
          {isPending ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Loading notifications…</p>
          ) : data && data.length > 0 ? (
            <ul className="divide-y">
              {data.map((n) => (
                <li key={n.id} className="flex gap-3 px-4 py-3">
                  <span
                    aria-hidden="true"
                    className={`mt-1.5 size-2 shrink-0 rounded-full ${n.read ? "bg-border" : "bg-primary"}`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{n.title}</p>
                    <p className="text-sm text-muted-foreground">{n.body}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{dateTimeFmt(n.createdAt)}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              You have no notifications yet.
            </p>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
