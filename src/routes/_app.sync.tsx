import { createFileRoute } from "@tanstack/react-router";
import { CloudOff, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, OfflineNotice } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { useOfflineQueue } from "@/hooks/use-offline-queue";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { dateTimeFmt } from "@/lib/format";

export const Route = createFileRoute("/_app/sync")({
  head: () => ({
    meta: [
      { title: "Sync centre — Frontline Nexus" },
      {
        name: "description",
        content: "Records saved on this device and their synchronisation status.",
      },
      { property: "og:title", content: "Sync centre — Frontline Nexus" },
      {
        property: "og:description",
        content: "Records saved on this device and their synchronisation status.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: SyncPage,
});

function SyncPage() {
  const online = useOnlineStatus();
  const { queue, pendingCount, failedCount, syncing, sync } = useOfflineQueue();

  const handleSync = async () => {
    const result = await sync();
    if (result.synced && !result.failed) toast.success(`${result.synced} record(s) synced`);
    else if (result.failed)
      toast.error(`${result.failed} record(s) could not sync. We'll retry automatically.`);
    else toast.success("Everything is already up to date");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sync centre"
        description="Attendance and assessments you saved without internet stay safe on this device until they reach the school records."
        actions={
          <Button
            onClick={() => void handleSync()}
            disabled={syncing || !online || queue.length === 0}
          >
            <RefreshCw className={syncing ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
            {syncing ? "Syncing…" : "Sync now"}
          </Button>
        }
      />

      {!online ? <OfflineNotice /> : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Saved on this device"
          value={queue.length}
          hint="Total records held locally"
        />
        <StatCard
          label="Waiting to sync"
          value={pendingCount}
          tone={pendingCount ? "warning" : "success"}
          hint="Will upload automatically"
        />
        <StatCard
          label="Needs attention"
          value={failedCount}
          tone={failedCount ? "danger" : "success"}
          hint="Failed uploads to retry"
        />
      </div>

      {queue.length === 0 ? (
        <EmptyState
          title="Nothing waiting to sync"
          description="Every register and assessment you've taken has reached the school records."
          icon={<CloudOff className="size-6" aria-hidden="true" />}
        />
      ) : (
        <ul className="fn-panel divide-y">
          {queue.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {item.className} attendance{item.subject ? ` · ${item.subject}` : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  {item.date} · {item.records.length} students · saved{" "}
                  {dateTimeFmt(new Date(item.updatedAt).toISOString())}
                </p>
              </div>
              <StatusBadge status={item.syncState} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
