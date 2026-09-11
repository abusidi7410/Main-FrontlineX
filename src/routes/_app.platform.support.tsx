import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { LifeBuoy } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { dateTimeFmt } from "@/lib/format";

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

interface Ticket {
  id: string;
  school: string;
  subject: string;
  requester: string;
  status: "pending" | "under_review" | "verified";
  createdAt: string;
}

const INITIAL_TICKETS: Ticket[] = [
  {
    id: "TCK-2041",
    school: "Al-Noor Model Academy",
    subject: "Bank transfer not reflecting on invoice FN-83021",
    requester: "bursar@alnoor.edu.ng",
    status: "under_review",
    createdAt: new Date(Date.now() - 3_600_000).toISOString(),
  },
  {
    id: "TCK-2040",
    school: "Hilltop College",
    subject: "Need to move 42 students to a new arm",
    requester: "admin@hilltop.edu.ng",
    status: "pending",
    createdAt: new Date(Date.now() - 9_000_000).toISOString(),
  },
  {
    id: "TCK-2038",
    school: "Royal Crest Academy",
    subject: "Teacher app not syncing attendance after network drop",
    requester: "ict@royalcrest.edu.ng",
    status: "pending",
    createdAt: new Date(Date.now() - 18_000_000).toISOString(),
  },
  {
    id: "TCK-2035",
    school: "Greenfield Schools",
    subject: "Request upgrade to 801–1,000 students plan",
    requester: "principal@greenfield.edu.ng",
    status: "verified",
    createdAt: new Date(Date.now() - 72_000_000).toISOString(),
  },
];

function PlatformSupportPage() {
  const [tickets, setTickets] = useState(INITIAL_TICKETS);
  const [broadcastTitle, setBroadcastTitle] = useState("");
  const [broadcastBody, setBroadcastBody] = useState("");

  const open = tickets.filter((t) => t.status !== "verified");

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
          <StatCard label="Resolved today" value={tickets.length - open.length} tone="success" />
          <StatCard label="Median first response" value="38 min" hint="Target is under 1 hour" />
        </div>

        <section className="space-y-3">
          <h2 className="font-medium">Ticket queue</h2>
          <ul className="fn-panel divide-y">
            {tickets.map((ticket) => (
              <li key={ticket.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{ticket.subject}</p>
                  <p className="text-sm text-muted-foreground">
                    {ticket.id} · {ticket.school} · {ticket.requester} ·{" "}
                    {dateTimeFmt(ticket.createdAt)}
                  </p>
                </div>
                <StatusBadge status={ticket.status} />
                {ticket.status !== "verified" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setTickets((prev) =>
                        prev.map((t) => (t.id === ticket.id ? { ...t, status: "verified" } : t)),
                      );
                      toast.success(`${ticket.id} marked resolved`);
                    }}
                  >
                    Mark resolved
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
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
              toast.success("Broadcast queued for every active school");
              setBroadcastTitle("");
              setBroadcastBody("");
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
            <Button type="submit">Send broadcast</Button>
          </form>
        </section>
      </div>
    </PermissionGate>
  );
}
