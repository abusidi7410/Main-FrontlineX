import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ErrorState, ListSkeleton, OfflineNotice } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { queueAttendance } from "@/offline/store";
import { CLASS_OPTIONS, getRoster, submitAttendance } from "@/services/attendance.service";
import { cn } from "@/lib/utils";
import type { AttendanceStatus } from "@/types";

export const Route = createFileRoute("/_app/attendance")({
  head: () => ({
    meta: [
      { title: "Attendance — Frontline Nexus" },
      {
        name: "description",
        content:
          "Mark class attendance in seconds — it works offline and syncs when you reconnect.",
      },
      { property: "og:title", content: "Attendance — Frontline Nexus" },
      {
        property: "og:description",
        content: "Mark class attendance in seconds, online or offline.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AttendancePage,
});

const STATUSES: { value: AttendanceStatus; label: string; className: string }[] = [
  {
    value: "present",
    label: "P",
    className: "data-[on=true]:bg-success data-[on=true]:text-white",
  },
  {
    value: "absent",
    label: "A",
    className: "data-[on=true]:bg-destructive data-[on=true]:text-white",
  },
  { value: "late", label: "L", className: "data-[on=true]:bg-warning data-[on=true]:text-white" },
  {
    value: "excused",
    label: "E",
    className: "data-[on=true]:bg-primary data-[on=true]:text-primary-foreground",
  },
];

function AttendancePage() {
  const online = useOnlineStatus();
  const [className, setClassName] = useState(CLASS_OPTIONS[0] ?? "");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});

  const roster = useQuery({ queryKey: ["roster", className], queryFn: () => getRoster(className) });

  useEffect(() => {
    if (!roster.data) return;
    setMarks(Object.fromEntries(roster.data.map((s) => [s.id, "present" as AttendanceStatus])));
  }, [roster.data]);

  const save = useMutation({
    mutationFn: async () => {
      const submission = {
        id: `att_${className}_${date}`,
        className,
        date,
        records: Object.entries(marks).map(([studentId, status]) => ({ studentId, status })),
        syncState: "pending" as const,
        updatedAt: Date.now(),
      };
      if (!online) {
        await queueAttendance(submission);
        return { queued: true };
      }
      try {
        await submitAttendance(submission);
        return { queued: false };
      } catch {
        await queueAttendance(submission);
        return { queued: true };
      }
    },
    onSuccess: (result) => {
      if (result.queued) {
        toast.success("Saved on this device. It will sync automatically when you're back online.");
      } else {
        toast.success(`Attendance submitted for ${className}.`);
      }
    },
  });

  const counts = STATUSES.map((s) => ({
    ...s,
    count: Object.values(marks).filter((value) => value === s.value).length,
  }));

  return (
    <PermissionGate permission="attendance.write">
      <div className="space-y-6">
        <PageHeader
          title="Attendance"
          description="Tap once per student. Present is pre-selected, so you only change the exceptions."
        />

        {!online ? <OfflineNotice /> : null}

        <div className="fn-panel grid gap-4 p-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="class">Class</Label>
            <Select value={className} onValueChange={setClassName}>
              <SelectTrigger id="class" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLASS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="date">Date</Label>
            <Input
              id="date"
              type="date"
              className="h-12"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3" aria-live="polite">
          {counts.map((item) => (
            <p
              key={item.value}
              className="rounded-full border bg-surface px-4 py-2 text-sm font-medium"
            >
              {item.value === "present"
                ? "Present"
                : item.value === "absent"
                  ? "Absent"
                  : item.value === "late"
                    ? "Late"
                    : "Excused"}
              : <span className="tabular-nums">{item.count}</span>
            </p>
          ))}
        </div>

        {roster.isError ? (
          <ErrorState onRetry={() => void roster.refetch()} />
        ) : roster.isPending ? (
          <ListSkeleton rows={8} />
        ) : (
          <ul className="fn-panel divide-y">
            {roster.data.map((student) => (
              <li key={student.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {student.firstName} {student.lastName}
                  </p>
                  <p className="text-sm text-muted-foreground">{student.admissionNumber}</p>
                </div>
                <div
                  role="group"
                  aria-label={`Attendance for ${student.firstName} ${student.lastName}`}
                  className="flex gap-2"
                >
                  {STATUSES.map((status) => {
                    const on = marks[student.id] === status.value;
                    return (
                      <button
                        key={status.value}
                        type="button"
                        data-on={on}
                        aria-pressed={on}
                        aria-label={status.value}
                        onClick={() =>
                          setMarks((prev) => ({ ...prev, [student.id]: status.value }))
                        }
                        className={cn(
                          "size-12 rounded-xl border font-semibold transition-colors hover:bg-muted",
                          status.className,
                        )}
                      >
                        {status.label}
                      </button>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="sticky bottom-20 lg:bottom-6">
          <Button
            className="h-12 w-full text-base"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Submit attendance"}
          </Button>
        </div>
      </div>
    </PermissionGate>
  );
}
