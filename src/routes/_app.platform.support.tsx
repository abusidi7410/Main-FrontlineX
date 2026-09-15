import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LifeBuoy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { dateTimeFmt } from "@/lib/format";
import {
  createBroadcast,
  listBroadcasts,
  listSupportTickets,
  setSupportTicketStatus,
} from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/support")({
  head: () => ({
    meta: [
      { title: "Support — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Open support conversations from schools and the platform response queue.",
      },
      { property: "og:title", content: "Support — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Open support conversations from schools and the response queue.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSupportPage,
});

function PlatformSupportPage() {
  const queryClient = useQueryClient();
  const [broadcastTitle, setBroadcastTitle] = useState("");
  const [broadcastBody, setBroadcastBody] = useState("");

  const tickets = useQuery({
    queryKey: ["platform", "support", "tickets"],
    queryFn: listSupportTickets,
  });
  const broadcasts = useQuery({
    queryKey: ["platform", "support", "broadcasts"],
    queryFn: listBroadcasts,
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "pending" | "under_review" | "verified" }) =>
      setSupportTicketStatus(id, status),
    onSuccess: (ticket) => {
      toast.success(`${ticket.id} marked resolved`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "support", "tickets"] });
    },
    onError: () => toast.error("We couldn't update that ticket. Please try again."),
  });

  const broadcastMutation = useMutation({
    mutationFn: () => createBroadcast(broadcastTitle.trim(), broadcastBody.trim()),
    onSuccess: (item) => {
      toast.success(`${item.title} — queued for every active school`);
      setBroadcastTitle("");
      setBroadcastBody("");
      void queryClient.invalidateQueries({ queryKey: ["platform", "support", "broadcasts"] });
    },
    onError: () => toast.error("We couldn't send that broadcast. Please try again."),
  });

  const list = tickets.data ?? [];
  const open = list.filter((t) => t.status !== "verified");
  const resolved = list.length - open.length;

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Support"
          description="Requests coming in from schools, and announcements you can send to every tenant."
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Open tickets"
            value={open.length}
            tone={open.length ? "warning" : "success"}
            icon={<LifeBuoy className="size-5" aria-hidden="true" />}
          />
          <StatCard label="Resolved" value={resolved} tone="success" />
          <StatCard label="Broadcasts sent" value={broadcasts.data?.length ?? 0} hint="" />
        </div>

        <section className="space-y-3">
          <h2 className="font-medium">Ticket queue</h2>
          {tickets.isError ? (
            <ErrorState onRetry={() => void tickets.refetch()} />
          ) : tickets.isPending ? (
            <ListSkeleton />
          ) : list.length === 0 ? (
            <EmptyState
              title="No tickets yet"
              description="New requests from schools appear here."
            />
          ) : (
            <ul className="fn-panel divide-y">
              {list.map((ticket) => (
                <li key={ticket.id} className="flex flex-wrap items-center gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{ticket.subject}</p>
                    <p className="text-sm text-muted-foreground">
                      {ticket.id} · {ticket.school || "Platform"} · {ticket.requester} ·{" "}
                      {dateTimeFmt(ticket.createdAt)}
                    </p>
                  </div>
                  <StatusBadge status={ticket.status} />
                  {ticket.status !== "verified" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={resolveMutation.isPending}
                      onClick={() => resolveMutation.mutate({ id: ticket.id, status: "verified" })}
                    >
                      Mark resolved
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="font-medium">Sent broadcasts</h2>
          {broadcasts.isPending ? (
            <ListSkeleton />
          ) : (broadcasts.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing broadcast yet.</p>
          ) : (
            <ul className="fn-panel divide-y">
              {(broadcasts.data ?? []).map((item) => (
                <li key={item.id} className="p-4">
                  <p className="font-medium">{item.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{item.body}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {item.author} · {dateTimeFmt(item.createdAt)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-3 font-medium">Broadcast to all schools</h2>
          <form
            className="fn-panel space-y-4 p-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (!broadcastTitle.trim() || !broadcastBody.trim()) {
                toast.error("Add a title and a message before sending.");
                return;
              }
              broadcastMutation.mutate();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="broadcast-title">Title</Label>
              <Input
                id="broadcast-title"
                className="h-11"
                placeholder="Scheduled maintenance on Saturday"
                value={broadcastTitle}
                onChange={(event) => setBroadcastTitle(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="broadcast-body">Message</Label>
              <Textarea
                id="broadcast-body"
                rows={4}
                placeholder="Explain what is happening, when, and what schools should expect."
                value={broadcastBody}
                onChange={(event) => setBroadcastBody(event.target.value)}
              />
            </div>
            <Button type="submit" disabled={broadcastMutation.isPending}>
              {broadcastMutation.isPending ? "Sending…" : "Send broadcast"}
            </Button>
          </form>
        </section>
      </div>
    </PermissionGate>
  );
}
