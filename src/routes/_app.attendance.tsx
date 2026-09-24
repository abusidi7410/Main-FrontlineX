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
import { ApiRequestError } from "@/api/client";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { queueAttendance } from "@/offline/store";
import { getRoster, submitAttendance } from "@/services/attendance.service";
import { getAcademicStructure } from "@/services/academics.service";
import { ARMS, CLASSES } from "@/constants/reference";
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
  const academics = useQuery({ queryKey: ["academics"], queryFn: () => getAcademicStructure() });
  const classes = academics.data?.classes ?? CLASSES;

  const [className, setClassName] = useState(classes[0] ?? "");
  const [arm, setArm] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [subject, setSubject] = useState("");
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});

  const roster = useQuery({
    queryKey: ["roster", className, arm, date, subject],
    queryFn: () => getRoster({ className, arm, date, subject }),
    enabled: className !== "" && date !== "",
  });

  useEffect(() => {
    if (!roster.data) return;
    if (roster.data.taken) {
      setMarks(roster.data.existing);
    } else {
      setMarks(Object.fromEntries(roster.data.students.map((s) => [s.id, "present" as AttendanceStatus])));
    }
  }, [roster.data]);

  const save = useMutation({
    mutationFn: async () => {
      const submission = {
        id: `att_${className}_${arm || "all"}_${date}`,
        className,
        date,
        ...(subject ? { subject } : {}),
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
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 409) {
          throw error;
        }
        await queueAttendance(submission);
        return { queued: true };
      }
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 409) {
        toast.error(error.message || "Attendance for this class has already been recorded.");
        void roster.refetch();
      }
    },
    onSuccess: (result) => {
      if (result.queued) {
        toast.success("Saved on this device. It will sync automatically when you're back online.");
      } else {
        toast.success(`Attendance submitted for ${className}${arm ? ` ${arm}` : ""}.`);
      }
      void roster.refetch();
    },
  });

  const counts = STATUSES.map((s) => ({
    ...s,
    count: Object.values(marks).filter((value) => value === s.value).length,
  }));

  const lockable = roster.data?.taken ?? false;

  return (
    <PermissionGate permission="attendance.write">
      <div className="space-y-6">
        <PageHeader
          title="Attendance"
          description="Tap once per student. Present is pre-selected, so you only change the exceptions."
        />

        {!online ? <OfflineNotice /> : null}

        <div className="fn-panel grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="class">Class</Label>
            <Select
              value={className}
              onValueChange={(value) => {
                setClassName(value);
                setMarks({});
              }}
            >
              <SelectTrigger id="class" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {classes.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="arm">Arm</Label>
            <Select
              value={arm}
              onValueChange={(value) => {
                setArm(value);
                setMarks({});
              }}
            >
              <SelectTrigger id="arm" className="h-12">
                <SelectValue placeholder="All arms" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All arms</SelectItem>
                {ARMS.map((option) => (
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
          <div className="space-y-1.5">
            <Label htmlFor="subject">Subject (optional)</Label>
            <Input
              id="subject"
              className="h-12"
              placeholder="e.g. Mathematics"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
          </div>
        </div>

        {lockable ? (
          <div role="status" className="rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm">
            Attendance for {className}
            {arm ? ` ${arm}` : ""} on {date} has already been recorded and is shown below. It can
            only be taken once per class and date.
          </div>
        ) : null}

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
        ) : roster.data.students.length === 0 ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            No active students found in {className}
            {arm ? ` ${arm}` : ""}. Add students to this class first.
          </div>
        ) : (
          <ul className="fn-panel divide-y">
            {roster.data.students.map((student) => (
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
                        disabled={lockable}
                        onClick={() =>
                          setMarks((prev) => ({ ...prev, [student.id]: status.value }))
                        }
                        className={cn(
                          "size-12 rounded-xl border font-semibold transition-colors",
                          lockable ? "cursor-default opacity-70" : "hover:bg-muted",
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
            disabled={save.isPending || lockable}
            onClick={() => save.mutate()}
          >
            {save.isPending
              ? "Saving…"
              : lockable
                ? "Attendance already recorded"
                : "Submit attendance"}
          </Button>
        </div>
      </div>
    </PermissionGate>
  );
}