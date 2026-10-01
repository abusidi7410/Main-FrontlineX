import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CalendarOff,
  CalendarPlus,
  CalendarRange,
  Check,
  School,
  UserCheck,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ARMS } from "@/constants/reference";
import {
  addClass,
  addSubject,
  getAcademicStructure,
  removeClass,
  removeSubject,
  TERM_OPTIONS,
  updateSchoolCalendar,
  updateSessionTerm,
} from "@/services/academics.service";
import {
  assignClassTeacher,
  getClassTeachers,
  type ClassTeacherAssignment,
} from "@/services/attendance.service";
import { listStaff } from "@/services/staff.service";

/** Python weekday numbering, matching `School.attendance_weekend_days`. */
const WEEKDAYS = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

export const Route = createFileRoute("/_app/academics")({
  head: () => ({
    meta: [
      { title: "Academics — Frontline Nexus" },
      {
        name: "description",
        content:
          "Sessions, terms, classes, arms and subjects — the academic backbone of your school.",
      },
      { property: "og:title", content: "Academics — Frontline Nexus" },
      {
        property: "og:description",
        content: "Sessions, terms, classes, arms and subjects for your school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AcademicsPage,
});

function AcademicsPage() {
  const queryClient = useQueryClient();
  const [calendarWeekend, setCalendarWeekend] = useState<number[]>([]);
  const [closureDate, setClosureDate] = useState("");

  const query = useQuery({
    queryKey: ["academics"],
    queryFn: getAcademicStructure,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["academics"] });

  // Who is responsible for each register. Readable by anyone with academics.read
  // (the register screen names the class teacher), but only `staff.write` can
  // change it - which the API enforces regardless of what this renders.
  const teachersQuery = useQuery({
    queryKey: ["class-teachers"],
    queryFn: getClassTeachers,
  });
  const staffQuery = useQuery({
    queryKey: ["staff"],
    queryFn: listStaff,
  });

  const designate = useMutation({
    mutationFn: (input: { className: string; staffId?: string | undefined }) =>
      assignClassTeacher(
        input.staffId
          ? { className: input.className, staffId: input.staffId }
          : { className: input.className, assign: false },
      ),
    onSuccess: async (_data, input) => {
      toast.success(input.staffId ? "Class teacher updated." : "Class teacher removed.");
      await queryClient.invalidateQueries({ queryKey: ["class-teachers"] });
    },
    onError: () => toast.error("We couldn't update the class teacher. Please try again."),
  });

  const sessionTerm = useMutation({
    mutationFn: updateSessionTerm,
    onSuccess: async () => {
      toast.success("Session and term updated.");
      setOpenSessionTerm(false);
      await invalidate();
    },
    onError: () => toast.error("We couldn't update the session and term. Please try again."),
  });

  const addSubj = useMutation({
    mutationFn: addSubject,
    onSuccess: async () => {
      toast.success("Subject added.");
      setNewSubject("");
      await invalidate();
    },
    onError: () => toast.error("We couldn't add that subject. Please try again."),
  });

  const removeSubj = useMutation({
    mutationFn: removeSubject,
    onSuccess: async () => {
      toast.success("Subject removed.");
      await invalidate();
    },
    onError: () => toast.error("We couldn't remove that subject. Please try again."),
  });

  const addCls = useMutation({
    // Wrapped so the level stays out of the mutation's variable type.
    mutationFn: (name: string) => addClass(name),
    onSuccess: async () => {
      toast.success("Class added.");
      setNewClass("");
      await invalidate();
    },
    onError: () => toast.error("We couldn't add that class. Please try again."),
  });

  const removeCls = useMutation({
    mutationFn: removeClass,
    onSuccess: async () => {
      toast.success("Class removed.");
      await invalidate();
    },
    onError: () => toast.error("We couldn't remove that class. Please try again."),
  });

  const [openSessionTerm, setOpenSessionTerm] = useState(false);
  const [session, setSession] = useState("");
  const [term, setTerm] = useState("");
  const [newSubject, setNewSubject] = useState("");
  const [newClass, setNewClass] = useState("");
  const [calendarSeeded, setCalendarSeeded] = useState(false);

  const saveCalendar = useMutation({
    mutationFn: updateSchoolCalendar,
    onSuccess: async () => {
      toast.success("School calendar updated.");
      await invalidate();
    },
    onError: () => toast.error("We couldn't update the school calendar. Please try again."),
  });

  // Seed the non-teaching-day checkboxes from the server once the structure
  // arrives. Seeded only on the first load: re-seeding on every refetch would
  // silently discard unsaved edits.
  useEffect(() => {
    if (!calendarSeeded && query.data) {
      setCalendarWeekend(query.data.attendanceWeekendDays ?? []);
      setCalendarSeeded(true);
    }
  }, [query.data, calendarSeeded]);

  const openSessionTermDialog = () => {
    if (!structure) return;
    setSession(structure.session);
    setTerm(structure.term);
    setOpenSessionTerm(true);
  };

  if (query.isError) {
    return <ErrorState onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <CardsSkeleton count={2} />;

  const structure = query.data;
  const assignments: ClassTeacherAssignment[] = teachersQuery.data?.assignments ?? [];
  const teacherFor = (className: string) => assignments.find((row) => row.className === className);
  // Only an active teacher can be given a register: a suspended staff member
  // holding one would be unable to submit it, leaving the class unregistered.
  const activeTeachers = (staffQuery.data ?? []).filter(
    (member) => member.role === "teacher" && member.status === "active",
  );

  return (
    <PermissionGate permission="academics.read">
      <div className="space-y-6">
        <PageHeader
          title="Academic structure"
          description="Your current session and term drive every attendance record, result sheet and invoice."
        />

        <section className="fn-panel p-5" aria-labelledby="session-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                <CalendarRange className="size-5" />
              </span>
              <div>
                <h2 id="session-heading" className="font-semibold">
                  Current session
                </h2>
                <p className="mt-0.5 text-muted-foreground">
                  {structure.session} · {structure.term}
                </p>
              </div>
            </div>
            <IfAllowed permission="academics.write">
              <Button variant="outline" onClick={openSessionTermDialog}>
                Edit session &amp; term
              </Button>
            </IfAllowed>
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="fn-panel p-5" aria-labelledby="classes-heading">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                  <School className="size-5" />
                </span>
                <h2 id="classes-heading" className="font-semibold">
                  Classes and arms
                </h2>
              </div>
            </div>

            <ul className="mt-4 flex flex-wrap gap-2">
              {structure.classes.map((className) => (
                <li
                  key={className}
                  className="flex items-center gap-1.5 rounded-full border bg-surface py-1.5 pl-3 text-sm"
                >
                  <span>
                    {className} ({ARMS.join(", ")})
                  </span>
                  <IfAllowed permission="academics.write">
                    <ConfirmDialog
                      trigger={
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-6 text-muted-foreground hover:text-destructive"
                          aria-label={`Remove ${className}`}
                        >
                          <X className="size-4" aria-hidden="true" />
                        </Button>
                      }
                      title={`Remove ${className}?`}
                      description={`${className} will no longer appear anywhere on the platform. Make sure no students are enrolled in it first.`}
                      confirmLabel={`Remove ${className}`}
                      destructive
                      onConfirm={() => removeCls.mutate(className)}
                    />
                  </IfAllowed>
                </li>
              ))}
            </ul>

            <IfAllowed permission="academics.write">
              <div className="mt-4 flex items-center gap-2">
                <Input
                  className="h-10 flex-1"
                  placeholder="Add a class, e.g. SS 4"
                  aria-label="New class name"
                  value={newClass}
                  onChange={(event) => setNewClass(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && newClass.trim()) addCls.mutate(newClass);
                  }}
                />
                <Button
                  className="h-10"
                  onClick={() => newClass.trim() && addCls.mutate(newClass)}
                  disabled={!newClass.trim() || addCls.isPending}
                >
                  <Check className="size-4" aria-hidden="true" /> Add class
                </Button>
              </div>
            </IfAllowed>
          </section>

          <section className="fn-panel p-5" aria-labelledby="calendar-heading">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                <CalendarOff className="size-5" />
              </span>
              <div>
                <h2 id="calendar-heading" className="font-semibold">
                  School calendar
                </h2>
                <p className="mt-0.5 text-muted-foreground">
                  On a non-school day the register screen says so, instead of showing every class as
                  untaken.
                </p>
              </div>
            </div>

            <IfAllowed permission="academics.write">
              <fieldset className="mt-4">
                <legend className="text-sm font-medium">Non-teaching days</legend>
                <div className="mt-2 flex flex-wrap gap-3">
                  {WEEKDAYS.map((day) => (
                    <label key={day.value} className="flex items-center gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        className="size-4"
                        checked={calendarWeekend.includes(day.value)}
                        onChange={(event) =>
                          setCalendarWeekend((current) => {
                            const next = event.target.checked
                              ? [...current, day.value]
                              : current.filter((value) => value !== day.value);
                            return next.sort((a, b) => a - b);
                          })
                        }
                      />
                      {day.label}
                    </label>
                  ))}
                </div>
                <Button
                  className="mt-3"
                  size="sm"
                  onClick={() => saveCalendar.mutate({ attendanceWeekendDays: calendarWeekend })}
                  disabled={saveCalendar.isPending}
                >
                  Save non-teaching days
                </Button>
              </fieldset>

              <div className="mt-5">
                <Label htmlFor="closure-date" className="text-sm font-medium">
                  School closure
                </Label>
                <div className="mt-2 flex items-center gap-2">
                  <Input
                    id="closure-date"
                    type="date"
                    className="h-10 w-44"
                    value={closureDate}
                    onChange={(event) => setClosureDate(event.target.value)}
                  />
                  <Button
                    className="h-10"
                    variant="outline"
                    onClick={() =>
                      closureDate &&
                      saveCalendar.mutate({
                        nonSchoolDays: [...structure.nonSchoolDays, closureDate],
                      })
                    }
                    disabled={!closureDate || saveCalendar.isPending}
                  >
                    <CalendarPlus className="size-4" aria-hidden="true" /> Add closure
                  </Button>
                </div>
              </div>
            </IfAllowed>

            {structure.nonSchoolDays.length > 0 && (
              <ul className="mt-4 flex flex-wrap gap-2">
                {structure.nonSchoolDays.map((day) => (
                  <li
                    key={day}
                    className="flex items-center gap-1.5 rounded-full border bg-surface py-1.5 pl-3 text-sm"
                  >
                    {day}
                    <IfAllowed permission="academics.write">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-6 text-muted-foreground hover:text-destructive"
                        aria-label={`Remove closure ${day}`}
                        onClick={() =>
                          saveCalendar.mutate({
                            nonSchoolDays: structure.nonSchoolDays.filter((value) => value !== day),
                          })
                        }
                      >
                        <X className="size-4" aria-hidden="true" />
                      </Button>
                    </IfAllowed>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="fn-panel p-5" aria-labelledby="class-teachers-heading">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                <UserCheck className="size-5" />
              </span>
              <div>
                <h2 id="class-teachers-heading" className="font-semibold">
                  Class teachers
                </h2>
                <p className="mt-0.5 text-muted-foreground">
                  Only the class teacher can take a register.
                </p>
              </div>
            </div>

            {teachersQuery.isPending ? (
              <p className="mt-4 text-sm text-muted-foreground">Loading class teachers…</p>
            ) : teachersQuery.isError ? (
              <p className="mt-4 text-sm text-destructive">
                We couldn&apos;t load the class teachers.
              </p>
            ) : structure.classes.length === 0 ? (
              <p className="mt-4 text-sm text-muted-foreground">
                Add a class first, then name its teacher.
              </p>
            ) : (
              <ul className="mt-4 space-y-2">
                {structure.classes.map((className) => {
                  const assigned = teacherFor(className);
                  return (
                    <li
                      key={className}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
                    >
                      <span className="text-sm font-medium">{className}</span>
                      <IfAllowed
                        permission="staff.write"
                        fallback={
                          <span className="text-sm text-muted-foreground">
                            {assigned ? assigned.staffName : "No class teacher"}
                          </span>
                        }
                      >
                        <Select
                          aria-label={`Class teacher for ${className}`}
                          value={assigned?.staffId ?? ""}
                          onValueChange={(value) =>
                            designate.mutate(
                              value === "none" ? { className } : { className, staffId: value },
                            )
                          }
                        >
                          <SelectTrigger className="h-9 w-56" disabled={designate.isPending}>
                            <SelectValue placeholder="No class teacher" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">No class teacher</SelectItem>
                            {activeTeachers.map((member) => (
                              <SelectItem key={member.id} value={member.id}>
                                {member.fullName}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </IfAllowed>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="fn-panel p-5" aria-labelledby="subjects-heading">
            {" "}
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                <School className="size-5" />
              </span>
              <h2 id="subjects-heading" className="font-semibold">
                Subjects
              </h2>
            </div>
            <ul className="mt-4 flex flex-wrap gap-2">
              {structure.subjects.map((subject) => (
                <li
                  key={subject}
                  className="flex items-center gap-1.5 rounded-full border bg-surface py-1.5 pl-3 text-sm"
                >
                  <span>{subject}</span>
                  <IfAllowed permission="academics.write">
                    <ConfirmDialog
                      trigger={
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-6 text-muted-foreground hover:text-destructive"
                          aria-label={`Remove ${subject}`}
                        >
                          <X className="size-4" aria-hidden="true" />
                        </Button>
                      }
                      title={`Remove ${subject}?`}
                      description={`${subject} will no longer appear anywhere on the platform. Make sure no results are attached to it first.`}
                      confirmLabel={`Remove ${subject}`}
                      destructive
                      onConfirm={() => removeSubj.mutate(subject)}
                    />
                  </IfAllowed>
                </li>
              ))}
            </ul>
            <IfAllowed permission="academics.write">
              <div className="mt-4 flex items-center gap-2">
                <Input
                  className="h-10 flex-1"
                  placeholder="Add a subject, e.g. French"
                  aria-label="New subject name"
                  value={newSubject}
                  onChange={(event) => setNewSubject(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && newSubject.trim()) addSubj.mutate(newSubject);
                  }}
                />
                <Button
                  className="h-10"
                  onClick={() => newSubject.trim() && addSubj.mutate(newSubject)}
                  disabled={!newSubject.trim() || addSubj.isPending}
                >
                  <Check className="size-4" aria-hidden="true" /> Add subject
                </Button>
              </div>
            </IfAllowed>
          </section>
        </div>

        <Dialog open={openSessionTerm} onOpenChange={setOpenSessionTerm}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit session &amp; term</DialogTitle>
              <DialogDescription>
                Every record on the platform — attendance, results and invoices — is dated to the
                current session and term.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="session-input">Session</Label>
                <Input
                  id="session-input"
                  placeholder="e.g. 2026/2027"
                  value={session}
                  onChange={(event) => setSession(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="term-select">Term</Label>
                <Select value={term} onValueChange={setTerm}>
                  <SelectTrigger id="term-select" className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TERM_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setOpenSessionTerm(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => session.trim() && term && sessionTerm.mutate({ session, term })}
                disabled={
                  !session.trim() || !term || sessionTerm.isPending || session === structure.session
                }
              >
                {sessionTerm.isPending ? "Saving…" : "Save changes"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </PermissionGate>
  );
}
