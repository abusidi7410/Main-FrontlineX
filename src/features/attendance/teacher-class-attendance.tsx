import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { MapPin } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { getCurrentPosition, geolocationSupported } from "@/lib/geolocation";
import { cn } from "@/lib/utils";
import {
  checkInToClass,
  getMyClassAttendance,
  TEACHER_CHECKIN_META,
  type TeacherClassSession,
} from "@/services/attendance.service";

function clockTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * One timetabled lesson with its check-in state. The button is the whole
 * point of the row: one tap takes a GPS reading and posts it against this
 * lesson only — the server proves the lesson, the teacher and the campus.
 */
function SessionRow({
  session,
  onCheckedIn,
}: {
  session: TeacherClassSession;
  onCheckedIn: () => void;
}) {
  const online = useOnlineStatus();
  const meta = TEACHER_CHECKIN_META[session.status];

  const checkIn = useMutation({
    mutationFn: async () => {
      if (!online) {
        throw new Error("You're offline. Check in again once your connection returns.");
      }
      const fix = await getCurrentPosition();
      return checkInToClass({
        entryId: session.entryId,
        latitude: fix.latitude,
        longitude: fix.longitude,
        accuracy: fix.accuracy,
      });
    },
    onSuccess: (result) => {
      if (result.denied) {
        // The attempt is still recorded (so an admin can see it) — say so.
        toast.warning(result.deniedReason ?? "Check-in refused: outside the campus location.");
      } else if (result.status === "unverified") {
        toast.success("Checked in — no location fix, recorded without verification.");
      } else if (result.status === "late_verified") {
        toast.success(`Checked in late — ${result.minutesLate} minutes after the bell.`);
      } else {
        toast.success(`Checked in to ${session.className} ${session.subject}.`);
      }
      onCheckedIn();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "We couldn't record your check-in.");
    },
  });

  const checked = session.status !== "not_checked_in" && session.checkInAt != null;

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5 hover:bg-muted/40 sm:px-5">
      <span
        aria-hidden="true"
        className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-soft font-semibold text-primary"
      >
        {(session.period || "?").slice(0, 2).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          {session.className} · {session.subject}
        </p>
        <p className="truncate text-sm text-muted-foreground">
          {session.scheduledStart}–{session.scheduledEnd}
          {session.room ? ` · ${session.room}` : ""}
          {checked ? ` · in at ${clockTime(session.checkInAt)}` : ""}
        </p>
      </div>
      <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", meta.className)}>
        {meta.label}
      </span>
      {session.canCheckIn ? (
        <Button
          type="button"
          size="sm"
          className="h-9 shrink-0"
          disabled={checkIn.isPending || !geolocationSupported()}
          onClick={() => checkIn.mutate()}
        >
          {checkIn.isPending ? "Checking in…" : "Check in"}
        </Button>
      ) : null}
      {!session.studentRegisterTaken ? (
        <Link
          to="/attendance"
          className="shrink-0 text-sm font-medium text-primary hover:underline"
        >
          Register
        </Link>
      ) : null}
    </li>
  );
}

/**
 * "My Class Attendance": every lesson the teacher is timetabled for today,
 * with its independent check-in. This is deliberately separate from the daily
 * staff check-in (campus arrival) and from the student register — three
 * different facts, three different actions, never merged.
 */
export function TeacherClassAttendance({ fallback }: { fallback?: ReactNode }) {
  const queryClient = useQueryClient();
  const myDay = useQuery({
    queryKey: ["teacher-checkin", "my-day"],
    queryFn: getMyClassAttendance,
    // A teacher without a linked staff record gets a 400 from the server;
    // the fallback (plain timetable list) renders instead of an error wall.
    retry: false,
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["teacher-checkin"] });

  if (myDay.isError) {
    return fallback ?? null;
  }

  const sessions: TeacherClassSession[] = myDay.data?.sessions ?? [];
  const summary = myDay.data?.summary;

  return (
    <section className="fn-panel overflow-hidden" aria-labelledby="class-attendance-heading">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-4 sm:px-5">
        <div>
          <h2 id="class-attendance-heading" className="font-semibold">
            My class attendance
          </h2>
          <p className="text-sm text-muted-foreground">
            {myDay.data
              ? `Check in to each lesson as you arrive · ${myDay.data.staffName}`
              : "Loading today's lessons…"}
          </p>
        </div>
        {summary && summary.total > 0 ? (
          <p className="rounded-full border bg-surface px-3 py-1.5 text-sm font-medium">
            Checked in:{" "}
            <span className="tabular-nums">{summary.total - (summary["not_checked_in"] ?? 0)}</span>{" "}
            of <span className="tabular-nums">{summary.total}</span>
          </p>
        ) : null}
      </div>

      {myDay.isPending ? (
        <ul className="animate-pulse divide-y">
          {[0, 1].map((row) => (
            <li key={row} className="flex items-center gap-4 px-5 py-4">
              <span className="size-10 rounded-xl bg-muted" aria-hidden="true" />
              <span className="h-4 w-48 rounded bg-muted" aria-hidden="true" />
            </li>
          ))}
        </ul>
      ) : sessions.length === 0 ? (
        <p className="px-5 py-8 text-center text-muted-foreground">
          No lessons on your timetable today. Check your full timetable for the week.
        </p>
      ) : (
        <ul className="divide-y">
          {sessions.map((session) => (
            <SessionRow key={session.entryId} session={session} onCheckedIn={invalidate} />
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t px-4 py-3 sm:px-5">
        <Link to="/timetable" className="font-medium text-primary hover:underline">
          View full timetable
        </Link>
        <Link to="/attendance" className="font-medium text-primary hover:underline">
          Take attendance
        </Link>
        {!geolocationSupported() ? (
          <span className="text-xs text-muted-foreground">
            <MapPin className="mr-1 inline size-3.5" aria-hidden="true" />
            This device can't provide a location, so check-ins are recorded unverified.
          </span>
        ) : null}
      </div>
    </section>
  );
}

/** Plain timetable list, used when check-in isn't available (no staff record). */
export function TimetableLessonList({
  slots,
}: {
  slots: {
    id: string | number;
    className: string;
    subject: string;
    period: string;
    room: string;
  }[];
}) {
  return (
    <section className="fn-panel overflow-hidden" aria-labelledby="today-heading">
      <div className="border-b px-5 py-4">
        <h2 id="today-heading" className="font-semibold">
          Today's classes
        </h2>
      </div>
      {slots.length === 0 ? (
        <p className="px-5 py-8 text-center text-muted-foreground">
          You have no scheduled classes today. Check your full timetable for the week.
        </p>
      ) : (
        <ul className="divide-y">
          {slots.map((slot) => (
            <li
              key={slot.id}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4 hover:bg-muted/40"
            >
              <span
                aria-hidden="true"
                className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-soft font-semibold text-primary"
              >
                {(slot.period || "?").slice(0, 2).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {slot.className} · {slot.subject}
                </p>
                <p className="text-sm text-muted-foreground">
                  {slot.period} · {slot.room}
                </p>
              </div>
              <Link
                to="/attendance"
                className="inline-flex min-h-11 shrink-0 items-center rounded-full bg-primary px-5 font-medium text-primary-foreground shadow-[0_6px_14px_-6px_oklch(0.31_0.02_250/0.55),inset_0_1px_0_oklch(1_0_0/0.1)] transition-all duration-200 hover:-translate-y-px hover:bg-primary/90"
              >
                Take attendance
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t px-5 py-3">
        <Link to="/timetable" className="font-medium text-primary hover:underline">
          View full timetable
        </Link>
      </div>
    </section>
  );
}
