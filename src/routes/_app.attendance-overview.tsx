import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, CircleSlash, Clock } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
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
import { getAcademicStructure } from "@/services/academics.service";
import {
  correctAttendance,
  getAttendanceHistory,
  getAttendanceOverview,
  getStaffAttendance,
  reviewStaffAttendance,
} from "@/services/attendance.service";
import { reverseGeocode } from "@/services/school.service";
import { useAuthenticatedSession } from "@/auth/session";
import { LocationMap } from "@/components/common/location-map";
import type {
  AttendanceStatus,
  School,
  StaffAttendanceRecord,
  StaffAttendanceStatus,
} from "@/types";
import { cn } from "@/lib/utils";
import { schoolToday } from "@/lib/format";
import { invalidateEnrollmentQueries } from "@/lib/query-invalidation";

const STATUSES: AttendanceStatus[] = ["present", "absent", "late", "excused"];

export const Route = createFileRoute("/_app/attendance-overview")({
  head: () => ({
    meta: [
      { title: "Attendance overview — Frontline Nexus" },
      {
        name: "description",
        content: "See which classes have taken their register and which have not.",
      },
      { property: "og:title", content: "Attendance overview — Frontline Nexus" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AttendanceOverviewPage,
});

function today() {
  return schoolToday();
}

function AttendanceOverviewPage() {
  const [date, setDate] = useState(today);

  const overview = useQuery({
    queryKey: ["attendance-overview", date],
    queryFn: () => getAttendanceOverview(date),
  });

  return (
    <PermissionGate permission="attendance.read">
      <div className="space-y-6">
        <PageHeader
          title="Attendance overview"
          description="Which classes have submitted today's register, and which have not."
        />

        <div className="fn-panel grid gap-4 p-4 sm:grid-cols-3">
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
            <Label>Submitted</Label>
            <p className="flex h-12 items-center text-lg font-semibold tabular-nums">
              {overview.data ? `${overview.data.submitted} of ${overview.data.total}` : "—"}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>School day</Label>
            <p className="flex h-12 items-center text-lg font-semibold">
              {overview.data ? (overview.data.isSchoolDay ? "Yes" : "No") : "—"}
            </p>
          </div>
        </div>

        {overview.data && !overview.data.isSchoolDay ? (
          <div role="status" className="rounded-xl border border-border bg-muted px-4 py-3 text-sm">
            {date} is not a school day for this school, so an empty register list is expected.
          </div>
        ) : null}

        {overview.isError ? (
          <ErrorState onRetry={() => void overview.refetch()} />
        ) : overview.isPending ? (
          <ListSkeleton rows={6} />
        ) : overview.data.classes.length === 0 ? (
          <div className="fn-panel p-6 text-center text-muted-foreground">
            No classes configured for this school yet.
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {overview.data.classes.map((row) => {
              const done = row.submitted > 0;
              return (
                <li key={row.classId} className="fn-panel p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium">{row.className}</p>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                        done ? "bg-success-soft text-success" : "bg-muted text-muted-foreground",
                      )}
                    >
                      {done ? (
                        <CheckCircle2 className="size-3.5" aria-hidden="true" />
                      ) : (
                        <CircleSlash className="size-3.5" aria-hidden="true" />
                      )}
                      {done ? "Submitted" : "Not taken"}
                    </span>
                  </div>
                  {done ? (
                    <dl className="mt-3 grid grid-cols-4 gap-2 text-center text-sm">
                      {(["present", "absent", "late", "excused"] as const).map((key) => (
                        <div key={key} className="rounded-lg bg-muted/50 px-1 py-2">
                          <dt className="text-xs capitalize text-muted-foreground">{key}</dt>
                          <dd className="font-semibold tabular-nums">{row[key]}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="mt-3 flex items-center gap-1 text-sm text-muted-foreground">
                      <Clock className="size-3.5" aria-hidden="true" />
                      No register for this day
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <AttendanceHistory date={date} />

        <IfAllowed permission="attendance.staff.manage">
          <StaffAttendanceRecords initialDate={date} />
        </IfAllowed>
      </div>
    </PermissionGate>
  );
}

/**
 * Amend one already-taken mark.
 *
 * Gated on `attendance.correct`, and the reason is mandatory because the API
 * always writes an audit entry: a corrected register has to stay explainable
 * months later, which is only possible if the reason was captured at the time.
 */
function CorrectButton({
  recordId,
  currentStatus,
  onDone,
}: {
  recordId: number;
  currentStatus: AttendanceStatus;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AttendanceStatus>(currentStatus);
  const [reason, setReason] = useState("");
  const queryClient = useQueryClient();

  const correct = useMutation({
    mutationFn: () => correctAttendance({ recordId: String(recordId), status, reason }),
    onSuccess: async (result) => {
      toast.success(
        result.changed ? "Mark corrected and recorded in the audit log." : "No change to record.",
      );
      setOpen(false);
      setReason("");
      await invalidateEnrollmentQueries(queryClient, [["attendance-history"]]);
      onDone();
    },
    onError: () => toast.error("We couldn't correct that mark. Please try again."),
  });

  return (
    <IfAllowed permission="attendance.correct">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="h-9">
            Correct
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Correct this mark</DialogTitle>
            <DialogDescription>
              The change is recorded with your name, the old status and your reason.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor={`correct-status-${recordId}`}>Status</Label>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as AttendanceStatus)}
              >
                <SelectTrigger id={`correct-status-${recordId}`} className="h-11">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((option) => (
                    <SelectItem key={option} value={option}>
                      <span className="capitalize">{option}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`correct-reason-${recordId}`}>Reason</Label>
              <Input
                id={`correct-reason-${recordId}`}
                value={reason}
                placeholder="e.g. Marked absent in error"
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => correct.mutate()} disabled={!reason.trim() || correct.isPending}>
              Save correction
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </IfAllowed>
  );
}

function AttendanceHistory({ date }: { date: string }) {
  const [className, setClassName] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [date]);
  const academics = useQuery({ queryKey: ["academics"], queryFn: () => getAcademicStructure() });
  const classes = academics.data?.classes ?? [];

  const history = useQuery({
    queryKey: ["attendance-history", className, date, page],
    queryFn: () =>
      getAttendanceHistory({
        ...(className === "" ? {} : { className }),
        dateTo: date,
        page,
        pageSize: 25,
      }),
  });

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Recent history</h2>
          <p className="text-sm text-muted-foreground">Most recent registers up to {date}.</p>
        </div>
        <div className="w-full space-y-1.5 sm:w-56">
          <Label htmlFor="history-class">Class</Label>
          <Select
            value={className || "__all__"}
            onValueChange={(value) => {
              setClassName(value === "__all__" ? "" : value);
              setPage(1);
            }}
          >
            <SelectTrigger id="history-class" className="h-11">
              <SelectValue placeholder="All classes" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All classes</SelectItem>
              {classes.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {history.isError ? (
        <ErrorState onRetry={() => void history.refetch()} />
      ) : history.isPending ? (
        <ListSkeleton rows={5} />
      ) : (history.data?.records.length ?? 0) === 0 ? (
        <div className="fn-panel p-6 text-center text-muted-foreground">
          No attendance has been recorded for this period.
        </div>
      ) : (
        <ul className="fn-panel divide-y">
          {history.data.records.map((record) => (
            <li key={record.id} className="flex flex-wrap items-center gap-3 p-3 sm:p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{record.studentName}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {record.admissionNumber} · {record.className} · {record.date}
                </p>
              </div>
              <span
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium capitalize",
                  record.status === "present" && "bg-success-soft text-success",
                  record.status === "absent" && "bg-destructive-soft text-destructive",
                  record.status === "late" && "bg-warning-soft text-warning",
                  record.status === "excused" && "bg-muted text-muted-foreground",
                )}
              >
                {record.status}
              </span>
              <CorrectButton
                recordId={record.id}
                currentStatus={record.status}
                onDone={() => void history.refetch()}
              />
            </li>
          ))}
        </ul>
      )}

      {history.data && history.data.totalPages > 1 ? (
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Page {history.data.page} of {history.data.totalPages} · {history.data.count} records
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page <= 1 || history.isFetching}
              onClick={() => setPage((current) => current - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              disabled={page >= history.data.totalPages || history.isFetching}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

const STAFF_STATUS_META: Record<
  StaffAttendanceStatus,
  { label: string; className: string; dot: string }
> = {
  at_school: {
    label: "On campus",
    className: "bg-success-soft text-success",
    dot: "bg-success",
  },
  outside: {
    label: "Outside campus",
    className: "bg-destructive-soft text-destructive",
    dot: "bg-destructive",
  },
  pending_review: {
    label: "Needs review",
    className: "bg-warning-soft text-warning",
    dot: "bg-warning",
  },
  unverified: {
    label: "Unverified",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
};

/**
 * Every staff GPS check-in for a day, with the derived status. Managers can
 * settle the ambiguous "needs review" rows, and open any row on a map beside
 * the campus radius to see exactly where the person was.
 */
function StaffAttendanceRecords({ initialDate }: { initialDate: string }) {
  const { school } = useAuthenticatedSession();
  const [date, setDate] = useState(initialDate);
  const [status, setStatus] = useState<StaffAttendanceStatus | "all">("all");
  const [search, setSearch] = useState("");
  useEffect(() => setDate(initialDate), [initialDate]);

  const query = useQuery({
    queryKey: ["staff-attendance", "records", date, status, search],
    queryFn: () =>
      getStaffAttendance({
        date,
        ...(status === "all" ? {} : { status: [status] }),
        ...(search.trim() ? { search: search.trim() } : {}),
        pageSize: 100,
      }),
  });

  const records = query.data?.records ?? [];
  const counts = records.reduce<Record<string, number>>((acc, record) => {
    acc[record.status] = (acc[record.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Teacher attendance records</h2>
          <p className="text-sm text-muted-foreground">
            GPS check-ins verified against the campus location on {date}.
          </p>
        </div>
        <div className="flex w-full flex-wrap gap-3 sm:w-auto">
          <div className="w-full space-y-1.5 sm:w-40">
            <Label htmlFor="staff-records-date">Date</Label>
            <Input
              id="staff-records-date"
              type="date"
              className="h-11"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="w-full space-y-1.5 sm:w-44">
            <Label htmlFor="staff-records-status">Status</Label>
            <Select
              value={status}
              onValueChange={(value) => setStatus(value as StaffAttendanceStatus | "all")}
            >
              <SelectTrigger id="staff-records-status" className="h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {(Object.keys(STAFF_STATUS_META) as StaffAttendanceStatus[]).map((value) => (
                  <SelectItem key={value} value={value}>
                    {STAFF_STATUS_META[value].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-full space-y-1.5 sm:w-48">
            <Label htmlFor="staff-records-search">Find staff</Label>
            <Input
              id="staff-records-search"
              className="h-11"
              placeholder="Name"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
      </div>

      {records.length > 0 ? (
        <div className="flex flex-wrap gap-2" aria-live="polite">
          <p className="rounded-full border bg-surface px-3 py-1.5 text-sm font-medium">
            Total: <span className="tabular-nums">{records.length}</span>
          </p>
          {(Object.keys(STAFF_STATUS_META) as StaffAttendanceStatus[]).map((value) =>
            counts[value] ? (
              <p
                key={value}
                className="rounded-full border bg-surface px-3 py-1.5 text-sm font-medium"
              >
                {STAFF_STATUS_META[value].label}:{" "}
                <span className="tabular-nums">{counts[value]}</span>
              </p>
            ) : null,
          )}
        </div>
      ) : null}

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton rows={5} />
      ) : records.length === 0 ? (
        <div className="fn-panel p-6 text-center text-muted-foreground">
          No staff check-ins recorded for this day.
        </div>
      ) : (
        <ul className="fn-panel divide-y">
          {records.map((record) => (
            <StaffRecordRow key={record.id} record={record} school={school} />
          ))}
        </ul>
      )}
    </section>
  );
}

function StaffRecordRow({ record, school }: { record: StaffAttendanceRecord; school: School | null }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const queryClient = useQueryClient();
  const meta = STAFF_STATUS_META[record.status];
  const hasPoint = record.latitude != null && record.longitude != null;

  const place = useQuery({
    queryKey: ["reverse-geocode", record.latitude, record.longitude],
    queryFn: () => reverseGeocode(record.latitude as number, record.longitude as number),
    enabled: open && hasPoint,
    staleTime: Infinity,
    retry: false,
  });

  const review = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      reviewStaffAttendance({ id: record.id, decision, ...(note.trim() ? { note: note.trim() } : {}) }),
    onSuccess: () => {
      toast.success("Check-in reviewed");
      setOpen(false);
      setNote("");
      void queryClient.invalidateQueries({ queryKey: ["staff-attendance"] });
    },
    onError: () => toast.error("We couldn't save that review. Please try again."),
  });

  return (
    <li className="flex flex-wrap items-center gap-3 p-3 sm:p-4">
      <span className={cn("size-2.5 shrink-0 rounded-full", meta.dot)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{record.staffName}</p>
        <p className="truncate text-sm text-muted-foreground">
          {record.role}
          {record.checkInAt
            ? ` · ${new Date(record.checkInAt).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}`
            : ""}
          {record.distanceMeters != null
            ? ` · ${Math.round(record.distanceMeters)} m from campus`
            : ""}
        </p>
      </div>
      <span className={cn("rounded-full px-3 py-1 text-xs font-medium", meta.className)}>
        {meta.label}
      </span>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="h-9">
            {record.status === "pending_review" ? "Review" : "Location"}
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{record.staffName}</DialogTitle>
            <DialogDescription>
              {record.date} · {meta.label}
              {record.distanceMeters != null
                ? ` · ${Math.round(record.distanceMeters)} m from campus`
                : ""}
            </DialogDescription>
          </DialogHeader>

          {hasPoint ? (
            <LocationMap
              latitude={school?.latitude ?? null}
              longitude={school?.longitude ?? null}
              markers={[
                {
                  latitude: record.latitude as number,
                  longitude: record.longitude as number,
                  status: record.status,
                  label: record.staffName,
                },
              ]}
              radiusMeters={school?.attendanceRadius ?? 150}
              height={240}
              zoom={16}
            />
          ) : (
            <p className="rounded-lg border border-border bg-muted px-3 py-4 text-sm text-muted-foreground">
              This check-in carried no coordinates, so there is nothing to place on the map.
            </p>
          )}

          {hasPoint ? (
            <p className="text-sm text-muted-foreground">
              {place.isFetching
                ? "Looking up the nearest place…"
                : place.data?.label
                  ? place.data.label
                  : `Near ${Number(record.latitude).toFixed(5)}, ${Number(record.longitude).toFixed(5)}`}
            </p>
          ) : null}

          {record.reviewedBy ? (
            <p className="text-sm text-muted-foreground">
              Reviewed by {record.reviewedBy}
              {record.reviewNote ? ` — ${record.reviewNote}` : ""}
            </p>
          ) : null}

          {record.status === "pending_review" ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor={`review-note-${record.id}`}>Note (optional)</Label>
                <Input
                  id={`review-note-${record.id}`}
                  value={note}
                  placeholder="e.g. Confirmed at the gate"
                  onChange={(event) => setNote(event.target.value)}
                />
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  disabled={review.isPending}
                  onClick={() => review.mutate("reject")}
                >
                  Mark outside
                </Button>
                <Button disabled={review.isPending} onClick={() => review.mutate("approve")}>
                  {review.isPending ? "Saving…" : "Confirm on campus"}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Close
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </li>
  );
}
