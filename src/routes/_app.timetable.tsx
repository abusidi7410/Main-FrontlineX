import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { CalendarCog, Layers, UserRound } from "lucide-react";
import { useSession } from "@/auth/session";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LessonEditor, type LessonSlot } from "@/features/timetable/lesson-editor";
import { entryAt } from "@/features/timetable/grid-model";
import { SchoolDayDialog } from "@/features/timetable/school-day-dialog";
import { TimetableGrid } from "@/features/timetable/timetable-grid";
import { getTimetableGrid } from "@/services/school.service";
import type { TimetableEntry, TimetableWeekday } from "@/types";

export const Route = createFileRoute("/_app/timetable")({
  head: () => ({
    meta: [
      { title: "Timetable — Frontline Nexus" },
      {
        name: "description",
        content: "The weekly class timetable with periods, subjects, teachers and rooms.",
      },
      { property: "og:title", content: "Timetable — Frontline Nexus" },
      {
        property: "og:description",
        content: "Weekly class timetable with periods, subjects, teachers and rooms.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: TimetablePage,
});

type ScopeMode = "class" | "teacher" | "school";

function TimetablePage() {
  return (
    <PermissionGate permission="timetable.read">
      <TimetablePageContent />
    </PermissionGate>
  );
}

function TimetablePageContent() {
  const { can, role } = useSession();
  const canWrite = can("timetable.write");

  // A teacher has no business picking whose timetable to read, so their view is
  // fixed to the API's own default: their own week.
  const [mode, setMode] = useState<ScopeMode>(role === "teacher" ? "teacher" : "class");
  const [classId, setClassId] = useState<string>("");
  const [teacherId, setTeacherId] = useState<string>("");
  const [slot, setSlot] = useState<LessonSlot | null>(null);
  const [dayDialog, setDayDialog] = useState(false);

  const scope = useMemo(() => {
    if (mode === "class" && classId) return { classId };
    if (mode === "teacher" && teacherId) return { teacherId };
    return {};
  }, [mode, classId, teacherId]);

  const queryKey = ["timetable", scope] as const;
  const query = useQuery({ queryKey, queryFn: () => getTimetableGrid(scope) });
  const grid = query.data;

  // Land on the first class rather than an empty grid the first time the page is
  // opened. Deferred until data arrives so this cannot loop.
  useEffect(() => {
    if (mode === "class" && !classId && grid?.classes.length) {
      setClassId(grid.classes[0]!.id);
    }
  }, [mode, classId, grid]);

  // Editing needs a class: a cell in a school-wide overview holds lessons for
  // many classes, so it is a summary rather than a slot you can fill in.
  const editingClassId = mode === "class" ? classId : "";
  const activeEntry: TimetableEntry | undefined = useMemo(() => {
    if (!slot || !editingClassId) return undefined;
    return entryAt(grid?.entries ?? [], slot.weekday, slot.periodId, editingClassId);
  }, [grid, slot, editingClassId]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timetable"
        description="Who teaches what, when, and where. Double bookings are refused as you build."
      />

      <div className="fn-panel flex flex-col gap-4 p-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="timetable-scope">Show</Label>
            <Select
              value={mode}
              // A teacher is scoped to their own week by the API, and a pupil or
              // parent to their own classes, so offering them a wider choice
              // would only produce an error.
              disabled={role !== "school_admin" && role !== "principal"}
              onValueChange={(next) => setMode(next as ScopeMode)}
            >
              <SelectTrigger id="timetable-scope" className="h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="class">
                  <span className="flex items-center gap-2">
                    <Layers className="size-4" aria-hidden="true" /> One class
                  </span>
                </SelectItem>
                <SelectItem value="teacher">
                  <span className="flex items-center gap-2">
                    <UserRound className="size-4" aria-hidden="true" /> One teacher
                  </span>
                </SelectItem>
                <SelectItem value="school">
                  <span className="flex items-center gap-2">
                    <CalendarCog className="size-4" aria-hidden="true" /> Every class
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {mode === "class" ? (
            <div className="space-y-1.5">
              <Label htmlFor="timetable-class">Class</Label>
              <Select value={classId} onValueChange={setClassId}>
                <SelectTrigger id="timetable-class" className="h-11">
                  <SelectValue placeholder="Select a class" />
                </SelectTrigger>
                <SelectContent>
                  {grid?.classes.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {mode === "teacher" && role !== "teacher" ? (
            <div className="space-y-1.5">
              <Label htmlFor="timetable-teacher">Teacher</Label>
              <Select value={teacherId} onValueChange={setTeacherId}>
                <SelectTrigger id="timetable-teacher" className="h-11">
                  <SelectValue placeholder="Select a teacher" />
                </SelectTrigger>
                <SelectContent>
                  {grid?.teachers.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>

        <IfAllowed permission="timetable.write">
          <Button variant="outline" onClick={() => setDayDialog(true)}>
            <CalendarCog className="size-4" aria-hidden="true" />
            School day
          </Button>
        </IfAllowed>
      </div>

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending || !grid ? (
        <ListSkeleton rows={6} />
      ) : grid.classes.length === 0 ? (
        <EmptyState
          title="No classes yet"
          description="Set up your classes in Academics first, then come back to build the timetable."
        />
      ) : (
        <>
          <TimetableGrid
            days={grid.days as TimetableWeekday[]}
            periods={grid.periods}
            entries={grid.entries}
            editable={canWrite && editingClassId !== ""}
            onSelectSlot={(weekday, periodId) => setSlot({ weekday, periodId })}
          />
          <p className="text-sm text-muted-foreground">
            {grid.entries.length} {grid.entries.length === 1 ? "lesson" : "lessons"} across{" "}
            {grid.days.length} teaching days
            {grid.session ? ` · ${grid.session} ${grid.term}`.trim() : ""}.
            {canWrite && editingClassId ? " Select any empty slot to add a lesson." : ""}
          </p>
        </>
      )}

      {grid && slot && editingClassId ? (
        <LessonEditor
          open={slot !== null}
          onOpenChange={(next) => !next && setSlot(null)}
          slot={slot}
          grid={grid}
          existing={activeEntry}
          classId={editingClassId}
        />
      ) : null}

      {grid ? (
        <SchoolDayDialog open={dayDialog} onOpenChange={setDayDialog} periods={grid.periods} />
      ) : null}
    </div>
  );
}
