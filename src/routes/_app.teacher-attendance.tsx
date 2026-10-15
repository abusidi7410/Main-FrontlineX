import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { TablePager } from "@/components/common/table-pager";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebounced } from "@/hooks/use-debounced";
import { schoolToday } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  decideTeacherCheckIn,
  getTeacherCheckIns,
  TEACHER_CHECKIN_META,
  type TeacherCheckInRow,
  type TeacherCheckInStatus,
} from "@/services/attendance.service";
import { getStaff } from "@/services/school.service";

export const Route = createFileRoute("/_app/teacher-attendance")({
  head: () => ({
    meta: [
      { title: "Teacher attendance — Frontline Nexus" },
      {
        name: "description",
        content:
          "Timetabled lesson check-ins: who reached their class, from where, and who missed it.",
      },
      { property: "og:title", content: "Teacher attendance — Frontline Nexus" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: TeacherAttendancePage,
});

const STATUS_VALUES: TeacherCheckInStatus[] = [
  "present_verified",
  "late_verified",
  "unverified",
  "outside",
  "missed",
  "cancelled",
];

const PAGE_SIZE = 25;

function TeacherAttendancePage() {
  const [date, setDate] = useState(schoolToday());
  const [staffId, setStaffId] = useState("");
  const [status, setStatus] = useState<TeacherCheckInStatus | "all">("all");
  const [className, setClassName] = useState("");
  const [subject, setSubject] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebounced(search, 300);
  const debouncedClass = useDebounced(className, 300);
  const debouncedSubject = useDebounced(subject, 300);

  // Any filter change invalidates the current page number: page 4 of a new
  // filter set usually doesn't exist, and silently showing nothing is worse
  // than starting over.
  useEffect(
    () => setPage(1),
    [date, staffId, status, debouncedClass, debouncedSubject, debouncedSearch],
  );

  const staff = useQuery({ queryKey: ["staff"], queryFn: getStaff });
  const teachers = (staff.data ?? []).filter((member) => member.role === "teacher");

  const query = useQuery({
    queryKey: [
      "teacher-checkins",
      date,
      staffId,
      status,
      debouncedClass,
      debouncedSubject,
      debouncedSearch,
      page,
    ],
    queryFn: () =>
      getTeacherCheckIns({
        date,
        ...(staffId ? { staffId } : {}),
        ...(status === "all" ? {} : { status: [status] }),
        ...(debouncedClass.trim() ? { className: debouncedClass.trim() } : {}),
        ...(debouncedSubject.trim() ? { subject: debouncedSubject.trim() } : {}),
        ...(debouncedSearch.trim() ? { search: debouncedSearch.trim() } : {}),
        page,
        pageSize: PAGE_SIZE,
      }),
  });

  const records = query.data?.records ?? [];
  const counts = query.data?.summary.counts ?? {};

  return (
    <PermissionGate permission="attendance.staff.manage">
      <div className="space-y-6">
        <PageHeader
          title="Teacher attendance"
          description="One row per timetabled lesson — check-ins verified against the campus, misses after the grace period."
        />

        <div className="fn-panel grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <div className="space-y-1.5">
            <Label htmlFor="ta-date">Date</Label>
            <Input
              id="ta-date"
              type="date"
              className="h-11"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ta-teacher">Teacher</Label>
            <Select
              value={staffId}
              onValueChange={(value) => setStaffId(value === "all" ? "" : value)}
            >
              <SelectTrigger id="ta-teacher" className="h-11">
                <SelectValue placeholder="All teachers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All teachers</SelectItem>
                {teachers.map((member) => (
                  <SelectItem key={member.id} value={member.id}>
                    {member.fullName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ta-status">Status</Label>
            <Select
              value={status}
              onValueChange={(value) => setStatus(value as TeacherCheckInStatus | "all")}
            >
              <SelectTrigger id="ta-status" className="h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {STATUS_VALUES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {TEACHER_CHECKIN_META[value].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ta-class">Class</Label>
            <Input
              id="ta-class"
              className="h-11"
              placeholder="e.g. JSS 1"
              value={className}
              onChange={(event) => setClassName(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ta-subject">Subject</Label>
            <Input
              id="ta-subject"
              className="h-11"
              placeholder="e.g. Mathematics"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ta-search">Find teacher</Label>
            <Input
              id="ta-search"
              className="h-11"
              placeholder="Name"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {query.data && query.data.summary.total > 0 ? (
          <div className="flex flex-wrap gap-2" aria-live="polite">
            <p className="rounded-full border bg-surface px-3 py-1.5 text-sm font-medium">
              Sessions: <span className="tabular-nums">{query.data.summary.total}</span>
            </p>
            {STATUS_VALUES.map((value) =>
              counts[value] ? (
                <p
                  key={value}
                  className="rounded-full border bg-surface px-3 py-1.5 text-sm font-medium"
                >
                  {TEACHER_CHECKIN_META[value].label}:{" "}
                  <span className="tabular-nums">{counts[value]}</span>
                </p>
              ) : null,
            )}
          </div>
        ) : null}

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton rows={6} />
        ) : records.length === 0 ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            No timetabled sessions match this day and these filters.
          </div>
        ) : (
          <>
            <ul className="fn-panel divide-y">
              {records.map((record) => (
                <CheckInRow key={record.id} record={record} />
              ))}
            </ul>
            <TablePager
              page={query.data.page}
              pageSize={query.data.pageSize}
              count={query.data.count}
              onPageChange={setPage}
              itemLabel="sessions"
              disabled={query.isFetching}
            />
          </>
        )}
      </div>
    </PermissionGate>
  );
}

function CheckInRow({ record }: { record: TeacherCheckInRow }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [overrideStatus, setOverrideStatus] = useState<
    "present_verified" | "late_verified" | "unverified" | ""
  >("");
  const meta = TEACHER_CHECKIN_META[record.status];

  const decide = useMutation({
    mutationFn: (input: { action: "cancel" | "override" }) =>
      decideTeacherCheckIn({
        id: record.id,
        action: input.action,
        ...(input.action === "override"
          ? { status: overrideStatus as "present_verified" | "late_verified" | "unverified" }
          : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      }),
    onSuccess: (_result, input) => {
      toast.success(input.action === "cancel" ? "Lesson marked as cancelled" : "Status overridden");
      setOpen(false);
      setNote("");
      setOverrideStatus("");
      void queryClient.invalidateQueries({ queryKey: ["teacher-checkins"] });
    },
    onError: (error) => {
      toast.error(
        error instanceof Error
          ? error.message
          : "We couldn't save that decision. Please try again.",
      );
    },
  });

  const overrideReady = overrideStatus !== "" && note.trim() !== "";
  const decided = record.decidedAt != null;

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3 sm:p-4">
      <span className={cn("size-2.5 shrink-0 rounded-full", meta.dot)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          {record.staffName}{" "}
          <span className="font-normal text-muted-foreground">
            · {record.className}
            {record.subject ? ` ${record.subject}` : ""}
          </span>
        </p>
        <p className="truncate text-sm text-muted-foreground">
          {record.period ? `${record.period} · ` : ""}
          {record.scheduledStart}–{record.scheduledEnd}
          {record.checkInAt
            ? ` · checked in ${new Date(record.checkInAt).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}${record.minutesLate != null && record.minutesLate > 0 ? ` (+${record.minutesLate}m late)` : ""}`
            : " · no check-in"}
          {record.distanceMeters != null ? ` · ${Math.round(record.distanceMeters)} m away` : ""}
          {record.lateAlertSent ? " · alert sent" : ""}
        </p>
        {decided ? (
          <p className="truncate text-xs text-muted-foreground">
            {record.decidedBy ? `Decided by ${record.decidedBy}` : "Decided"}
            {record.decisionNote ? ` — ${record.decisionNote}` : ""}
          </p>
        ) : null}
      </div>
      <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", meta.className)}>
        {meta.label}
      </span>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setNote("");
            setOverrideStatus("");
          }
        }}
      >
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="h-9">
            Decide
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {record.staffName} · {record.className}
            </DialogTitle>
            <DialogDescription>
              {record.date} · {record.scheduledStart}–{record.scheduledEnd}
              {record.subject ? ` · ${record.subject}` : ""} — currently {meta.label.toLowerCase()}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor={`decision-note-${record.id}`}>
              Reason {record.status === "cancelled" ? "(optional)" : "— required for an override"}
            </Label>
            <Input
              id={`decision-note-${record.id}`}
              value={note}
              placeholder="e.g. Traffic confirmed by phone call"
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`override-status-${record.id}`}>Override to</Label>
            <Select
              value={overrideStatus}
              onValueChange={(value) =>
                setOverrideStatus(value as "present_verified" | "late_verified" | "unverified" | "")
              }
            >
              <SelectTrigger id={`override-status-${record.id}`} className="h-11">
                <SelectValue placeholder="Choose a status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="present_verified">
                  {TEACHER_CHECKIN_META.present_verified.label}
                </SelectItem>
                <SelectItem value="late_verified">
                  {TEACHER_CHECKIN_META.late_verified.label}
                </SelectItem>
                <SelectItem value="unverified">{TEACHER_CHECKIN_META.unverified.label}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              disabled={decide.isPending || record.status === "cancelled"}
              onClick={() => decide.mutate({ action: "cancel" })}
            >
              {record.status === "cancelled" ? "Already cancelled" : "Mark lesson cancelled"}
            </Button>
            <Button
              type="button"
              disabled={decide.isPending || !overrideReady}
              onClick={() => decide.mutate({ action: "override" })}
            >
              {decide.isPending ? "Saving…" : "Override status"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}
