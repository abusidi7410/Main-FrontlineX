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
} from "@/services/attendance.service";
import type { AttendanceStatus } from "@/types";
import { cn } from "@/lib/utils";
import { schoolToday } from "@/lib/format";

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
      await queryClient.invalidateQueries({ queryKey: ["attendance-history"] });
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
