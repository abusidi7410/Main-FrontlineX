import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
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
import { schoolToday } from "@/lib/format";
import { cn } from "@/lib/utils";
import { invalidateEnrollmentQueries } from "@/lib/query-invalidation";
import type { AttendanceStatus } from "@/types";

export const Route = createFileRoute("/_app/attendance")({
  head: () => ({
    meta: [
      { title: "Attendance — Frontline Nexus" },
      {
        name: "description",
        content:
          "Take the day's class register in seconds — it works offline and syncs when you reconnect.",
      },
      { property: "og:title", content: "Attendance — Frontline Nexus" },
      {
        property: "og:description",
        content: "Take the day's class register in seconds, online or offline.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AttendancePage,
});

// Single-letter buttons, because on a phone the label is read by the eye first
// and the letter by the thumb. `aria-label` carries the full word for screen
// readers and for anyone who does not know the shorthand.
const STATUSES: { value: AttendanceStatus; label: string; word: string; className: string }[] = [
  {
    value: "present",
    label: "P",
    word: "Present",
    className: "data-[on=true]:bg-success data-[on=true]:text-white",
  },
  {
    value: "absent",
    label: "A",
    word: "Absent",
    className: "data-[on=true]:bg-destructive data-[on=true]:text-white",
  },
  {
    value: "late",
    label: "L",
    word: "Late",
    className: "data-[on=true]:bg-warning data-[on=true]:text-white",
  },
  {
    value: "excused",
    label: "E",
    word: "Excused",
    className: "data-[on=true]:bg-primary data-[on=true]:text-primary-foreground",
  },
];

function today() {
  return schoolToday();
}

function AttendancePage() {
  const online = useOnlineStatus();
  const queryClient = useQueryClient();
  const academics = useQuery({ queryKey: ["academics"], queryFn: () => getAcademicStructure() });

  // Only classes the school actually configured. The old hardcoded fallback list
  // offered 14 seeded names, which is how a dropdown could offer a class the
  // roster then refused to load.
  const classes = useMemo(() => academics.data?.classes ?? [], [academics.data?.classes]);
  const [className, setClassName] = useState("");
  const [arm, setArm] = useState("");
  const [date, setDate] = useState(today);
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});
  const [search, setSearch] = useState("");

  // Default to the first real class once academics land, rather than a guessed one.
  useEffect(() => {
    const first = classes[0];
    if (className === "" && first !== undefined) setClassName(first);
  }, [classes, className]);

  const roster = useQuery({
    queryKey: ["roster", className, arm, date],
    queryFn: () => getRoster({ className, arm, date }),
    enabled: className !== "" && date !== "",
  });

  const students = useMemo(() => roster.data?.students ?? [], [roster.data?.students]);
  const taken = roster.data?.taken ?? false;

  // An already-taken register loads for editing. An untaken one defaults every
  // student to Present, so a teacher only ever touches the exceptions.
  useEffect(() => {
    if (!roster.data) return;
    if (roster.data.taken) {
      setMarks(roster.data.existing);
    } else {
      setMarks(
        Object.fromEntries(roster.data.students.map((s) => [s.id, "present" as AttendanceStatus])),
      );
    }
  }, [roster.data]);

  // Read-only when the register is already taken, or when this teacher is not
  // the class's designated class teacher, or the school is closed today.
  const locked = taken;
  const readOnly = taken || roster.data?.canSubmit === false || roster.data?.isSchoolDay === false;

  const save = useMutation({
    mutationFn: async () => {
      const submission = {
        // One register per class per school day, so this id is also the
        // offline-queue key: re-marking the same day replaces the pending entry.
        id: `att_${className}_${arm || "all"}_${date}`,
        className,
        date,
        ...(arm ? { arm } : {}),
        records: students.map((student) => ({
          studentId: student.id,
          status: marks[student.id] ?? ("present" as AttendanceStatus),
        })),
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
        // A 409 means someone else already took this register. Queueing it would
        // only produce a second failure on sync, so surface it instead.
        if (error instanceof ApiRequestError && error.status === 409) throw error;
        if (error instanceof ApiRequestError && error.status !== 0 && error.status < 500) {
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
        return;
      }
      if (error instanceof ApiRequestError && error.status === 403) {
        toast.error("Only this class's class teacher can submit its register.");
        return;
      }
      toast.error(error instanceof Error ? error.message : "Could not save attendance.");
    },
    onSuccess: (result) => {
      if (result.queued) {
        toast.success("Saved on this device. It will sync automatically when you're back online.");
      } else {
        toast.success(`Attendance submitted for ${className}${arm ? ` ${arm}` : ""}.`);
      }
      void roster.refetch();
      // Attendance feeds the students list percentage, the overview, and the
      // history page — all derive from the same records, so refresh them all.
      void invalidateEnrollmentQueries(queryClient);
    },
  });

  const counts = useMemo(
    () =>
      STATUSES.map((status) => ({
        ...status,
        count: students.filter((student) => (marks[student.id] ?? "present") === status.value)
          .length,
      })),
    [marks, students],
  );

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (needle === "") return students;
    return students.filter((student) =>
      `${student.firstName} ${student.lastName} ${student.admissionNumber} ${student.arm}`
        .toLowerCase()
        .includes(needle),
    );
  }, [search, students]);

  function setAll(value: AttendanceStatus) {
    if (readOnly) return;
    setMarks(Object.fromEntries(students.map((student) => [student.id, value])));
  }

  return (
    <PermissionGate permission="attendance.read">
      <div className="space-y-4 pb-24 lg:space-y-6">
        <PageHeader
          title="Attendance"
          description="Present is pre-selected, so you only change the exceptions."
        />

        {!online ? <OfflineNotice /> : null}

        {classes.length === 0 && !academics.isPending ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            This school has no classes configured yet. Add one under Academics before taking
            attendance.
          </div>
        ) : null}

        <div className="fn-panel grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="class">Class</Label>
            <Select
              value={className}
              onValueChange={(value) => {
                setClassName(value);
                setArm("");
                setMarks({});
                setSearch("");
              }}
            >
              <SelectTrigger id="class" className="h-12">
                <SelectValue placeholder="Select class" />
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
                <SelectValue placeholder="Whole class" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Whole class</SelectItem>
                {(roster.data?.sections ?? []).map((option) => (
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
            <Label htmlFor="search">Find student</Label>
            <Input
              id="search"
              className="h-12"
              placeholder="Name or admission number"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {roster.data?.isSchoolDay === false ? (
          <div role="status" className="rounded-xl border border-border bg-muted px-4 py-3 text-sm">
            {date} is not a school day for this school, so the register is read-only.
          </div>
        ) : null}

        {roster.data && roster.data.canSubmit === false ? (
          <div
            role="status"
            className="rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm"
          >
            {roster.data.classTeacher
              ? `${roster.data.classTeacher} is the class teacher for ${className}.`
              : `No class teacher is assigned to ${className} yet.`}{" "}
            You can view this register but not submit it.
          </div>
        ) : null}

        {locked ? (
          <div
            role="status"
            className="rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm"
          >
            Attendance for {className}
            {arm ? ` ${arm}` : ""} on {date} has already been recorded and is shown below. It can
            only be taken once per class per day.
          </div>
        ) : null}

        {students.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-11"
              disabled={readOnly}
              onClick={() => setAll("present")}
            >
              All present
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11"
              disabled={readOnly}
              onClick={() => setAll("absent")}
            >
              All absent
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-11"
              disabled={readOnly}
              onClick={() =>
                setMarks(
                  Object.fromEntries(students.map((s) => [s.id, "present" as AttendanceStatus])),
                )
              }
            >
              Reset
            </Button>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2" aria-live="polite">
          {counts.map((item) => (
            <p
              key={item.value}
              className={cn(
                "rounded-full border bg-surface px-3 py-1.5 text-sm font-medium",
                item.count > 0 && item.value !== "present" && "border-warning/40",
              )}
            >
              {item.word}: <span className="tabular-nums">{item.count}</span>
            </p>
          ))}
        </div>

        {roster.isError ? (
          <ErrorState onRetry={() => void roster.refetch()} />
        ) : roster.isPending ? (
          <ListSkeleton rows={8} />
        ) : students.length === 0 ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            {roster.data?.classConfigured === false ? (
              <>
                {className} is configured on this school but has no class record or enrolled
                students yet.
              </>
            ) : (
              <>
                No students with an active enrollment in {className}
                {arm ? ` ${arm}` : ""}.
              </>
            )}
          </div>
        ) : visible.length === 0 ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            No student matches “{search}”.
          </div>
        ) : (
          <ul className="fn-panel divide-y">
            {visible.map((student) => {
              const current = marks[student.id] ?? "present";
              return (
                <li
                  key={student.id}
                  className="flex items-center gap-3 p-3 sm:p-4"
                  data-status={current}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {student.firstName} {student.lastName}
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      {student.admissionNumber}
                      {student.arm ? ` · ${student.arm}` : ""}
                    </p>
                  </div>
                  <div
                    role="group"
                    aria-label={`Attendance for ${student.firstName} ${student.lastName}`}
                    className="flex shrink-0 gap-1.5"
                  >
                    {STATUSES.map((status) => {
                      const on = current === status.value;
                      return (
                        <button
                          key={status.value}
                          type="button"
                          data-on={on}
                          aria-pressed={on}
                          aria-label={`${status.word} — ${student.firstName} ${student.lastName}`}
                          disabled={readOnly}
                          onClick={() =>
                            setMarks((prev) => ({ ...prev, [student.id]: status.value }))
                          }
                          className={cn(
                            "size-11 rounded-xl border text-sm font-semibold transition-colors sm:size-12",
                            readOnly ? "cursor-default opacity-70" : "hover:bg-muted",
                            status.className,
                          )}
                        >
                          {status.label}
                        </button>
                      );
                    })}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 p-3 backdrop-blur lg:static lg:z-auto lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <div className="mx-auto max-w-lg lg:max-w-none">
            <Button
              className="h-12 w-full text-base"
              disabled={save.isPending || readOnly || students.length === 0 || className === ""}
              onClick={() => save.mutate()}
            >
              {save.isPending
                ? "Saving…"
                : taken
                  ? "Attendance already recorded"
                  : roster.data?.isSchoolDay === false
                    ? "Not a school day"
                    : roster.data?.canSubmit === false
                      ? "View only"
                      : `Save attendance for ${students.length} students`}
            </Button>
          </div>
        </div>
      </div>
    </PermissionGate>
  );
}
