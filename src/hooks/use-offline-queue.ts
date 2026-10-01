import { useCallback, useEffect, useState } from "react";
import { listQueuedAttendance, markQueuedState, removeQueuedAttendance } from "@/offline/store";
import { ApiRequestError } from "@/api/client";
import { submitAttendance } from "@/services/attendance.service";
import type { AttendanceSubmission } from "@/types";

export function useOfflineQueue() {
  const [queue, setQueue] = useState<AttendanceSubmission[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const saved = await listQueuedAttendance();
      setQueue(saved);
      setQueueError(null);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Saved attendance on this device could not be read.";
      setQueueError(message);
      throw error;
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
    const onFocus = () => void refresh().catch(() => undefined);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const sync = useCallback(async () => {
    setSyncing(true);
    try {
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
            await removeQueuedAttendance(submission.id);
            synced += 1;
          } else {
            await markQueuedState(submission.id, "failed");
            failed += 1;
          }
        }
      }
      await refresh();
      return { synced, failed };
    } finally {
      setSyncing(false);
    }
  }, [refresh]);

  return {
    queue,
    pendingCount: queue.filter((q) => q.syncState === "pending").length,
    failedCount: queue.filter((q) => q.syncState === "failed").length,
    syncing,
    queueError,
    sync,
    refresh,
  };
}
