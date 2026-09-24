import { useCallback, useEffect, useState } from "react";
import { listQueuedAttendance, markQueuedState, removeQueuedAttendance } from "@/offline/store";
import { ApiRequestError } from "@/api/client";
import { submitAttendance } from "@/services/attendance.service";
import type { AttendanceSubmission } from "@/types";

export function useOfflineQueue() {
  const [queue, setQueue] = useState<AttendanceSubmission[]>([]);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(async () => {
    setQueue(await listQueuedAttendance());
  }, []);

  useEffect(() => {
    void refresh();
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const sync = useCallback(async () => {
    setSyncing(true);
    const pending = (await listQueuedAttendance()).filter((s) => s.syncState !== "synced");
    let synced = 0;
    let failed = 0;
    for (const submission of pending) {
      try {
        await submitAttendance(submission);
        await removeQueuedAttendance(submission.id);
        synced += 1;
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 409) {
          // Already recorded server-side (taken-once rule): treat as success.
          await removeQueuedAttendance(submission.id);
          synced += 1;
        } else {
          await markQueuedState(submission.id, "failed");
          failed += 1;
        }
      }
    }
    await refresh();
    setSyncing(false);
    return { synced, failed };
  }, [refresh]);

  return {
    queue,
    pendingCount: queue.filter((q) => q.syncState === "pending").length,
    failedCount: queue.filter((q) => q.syncState === "failed").length,
    syncing,
    sync,
    refresh,
  };
}
