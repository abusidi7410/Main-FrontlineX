import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
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
import {
  createTimetableEntry,
  deleteTimetableEntry,
  updateTimetableEntry,
} from "@/services/school.service";
import type { TimetableEntry, TimetableGrid } from "@/types";
import { TIMETABLE_WEEKDAY_NAMES } from "@/types";

const NO_TEACHER = "__none";
const NO_ROOM = "__none";

export type LessonSlot = { weekday: number; periodId: string };

/**
 * Create, change or remove the lesson in one (day, period) slot of one class.
 *
 * The class is fixed by the view the administrator came from, and the day and
 * period are fixed by the cell they clicked, so the editor only ever chooses
 * subject, teacher and room. Conflicts are not re-implemented here: the server
 * owns that rule and returns which field clashed, so the message a bursar reads
 * is the same one the database would have enforced.
 */
export function LessonEditor({
  open,
  onOpenChange,
  slot,
  grid,
  existing,
  classId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slot: LessonSlot | null;
  grid: TimetableGrid;
  existing: TimetableEntry | undefined;
  classId: string;
}) {
  const queryClient = useQueryClient();
  const period = grid.periods.find((row) => row.id === slot?.periodId);

  const [subject, setSubject] = useState("");
  const [teacherId, setTeacherId] = useState(NO_TEACHER);
  const [room, setRoom] = useState(NO_ROOM);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Re-seed the form whenever the dialog opens on a different lesson, otherwise
  // a slot the administrator has not visited yet would inherit the last one's
  // values.
  useEffect(() => {
    if (!open) return;
    setSubject(existing?.subject ?? "");
    setTeacherId(existing?.teacherId || NO_TEACHER);
    setRoom(existing?.room || NO_ROOM);
  }, [open, existing]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["timetable"] });

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        subject: subject.trim(),
        teacherId: teacherId === NO_TEACHER ? "" : teacherId,
        room: room === NO_ROOM ? "" : room,
      };
      if (existing) {
        return updateTimetableEntry(existing.id, body);
      }
      if (!slot) throw new Error("No slot selected");
      return createTimetableEntry({
        weekday: slot.weekday,
        periodId: slot.periodId,
        classId,
        ...body,
      });
    },
    onSuccess: async () => {
      toast.success(existing ? "Lesson updated." : "Lesson added to the timetable.");
      onOpenChange(false);
      await invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.fieldErrors) {
        // Surface the server's conflict message against the field it belongs to.
        const first = Object.values(error.fieldErrors)[0];
        toast.error(first ?? "We couldn't save that lesson.");
        return;
      }
      toast.error(
        error instanceof Error ? error.message : "We couldn't save that lesson. Please try again.",
      );
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteTimetableEntry(existing?.id ?? ""),
    onSuccess: async () => {
      toast.success("Lesson removed from the timetable.");
      setConfirmDelete(false);
      onOpenChange(false);
      await invalidate();
    },
    onError: (error) => {
      setConfirmDelete(false);
      toast.error(error instanceof Error ? error.message : "We couldn't remove that lesson.");
    },
  });

  if (!slot || !period) return null;

  const dayName = TIMETABLE_WEEKDAY_NAMES[slot.weekday as keyof typeof TIMETABLE_WEEKDAY_NAMES];
  const ready = subject.trim().length > 0 && !save.isPending;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{existing ? "Edit lesson" : "Add lesson"}</DialogTitle>
            <DialogDescription>
              {dayName} · {period.name} ({period.startTime}–{period.endTime}). We&apos;ll let you
              know if the teacher, class or room is already booked in this period.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="lesson-subject">Subject</Label>
              <Input
                id="lesson-subject"
                value={subject}
                list="timetable-subject-options"
                placeholder="e.g. Mathematics"
                onChange={(event) => setSubject(event.target.value)}
              />
              {/* A native datalist rather than a Select: it offers the school's
                  configured subjects while still allowing one that is not on the
                  list yet, without the two-control ambiguity of Select + Input. */}
              <datalist id="timetable-subject-options">
                {grid.subjects.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
              <p className="text-xs text-muted-foreground">
                {grid.subjects.length} subjects configured in Academics.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="lesson-teacher">Teacher</Label>
              <Select value={teacherId} onValueChange={setTeacherId}>
                <SelectTrigger id="lesson-teacher" className="h-11">
                  <SelectValue placeholder="Assign a teacher" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_TEACHER}>No teacher yet</SelectItem>
                  {grid.teachers.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="lesson-room">Room</Label>
              <Input
                id="lesson-room"
                value={room === NO_ROOM ? "" : room}
                list="timetable-room-options"
                placeholder="e.g. Room 1"
                onChange={(event) => setRoom(event.target.value || NO_ROOM)}
              />
              <datalist id="timetable-room-options">
                {grid.rooms.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>

          <DialogFooter className="sm:justify-between">
            {existing ? (
              <Button
                type="button"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                disabled={remove.isPending}
                onClick={() => setConfirmDelete(true)}
              >
                Remove lesson
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={!ready} onClick={() => save.mutate()}>
                {save.isPending ? "Saving…" : existing ? "Save changes" : "Add lesson"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Remove this lesson?"
        description="The slot goes back to being free. Nothing else on the timetable changes."
        confirmLabel="Remove lesson"
        destructive
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
