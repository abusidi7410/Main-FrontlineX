import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import { createTimetablePeriod, deleteTimetablePeriod } from "@/services/school.service";
import type { TimetablePeriod } from "@/types";

/**
 * The school's bell schedule: the periods every lesson is placed on.
 *
 * Kept in its own dialog because it is the one part of the timetable that is
 * about the school rather than about a class, and because renaming a period
 * would rewrite the meaning of every lesson on it -- so it is a deliberate,
 * separate action from filling in lessons.
 */
export function SchoolDayDialog({
  open,
  onOpenChange,
  periods,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  periods: TimetablePeriod[];
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [isBreak, setIsBreak] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<TimetablePeriod | null>(null);

  const reset = () => {
    setName("");
    setStart("");
    setEnd("");
    setIsBreak(false);
  };

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["timetable"] });

  const add = useMutation({
    mutationFn: () =>
      createTimetablePeriod({
        name: name.trim(),
        startTime: start,
        endTime: end,
        isBreak,
      }),
    onSuccess: async () => {
      toast.success(`${name.trim()} added to the school day.`);
      reset();
      await invalidate();
    },
    onError: (error) => {
      const message =
        error instanceof ApiRequestError && error.fieldErrors
          ? Object.values(error.fieldErrors)[0]
          : null;
      toast.error(message ?? "We couldn't add that period.");
    },
  });

  const remove = useMutation({
    mutationFn: (period: TimetablePeriod) => deleteTimetablePeriod(period.id),
    onSuccess: async () => {
      toast.success("Period removed from the school day.");
      setPendingDelete(null);
      await invalidate();
    },
    onError: (error) => {
      const message =
        error instanceof ApiRequestError && error.fieldErrors
          ? Object.values(error.fieldErrors)[0]
          : null;
      setPendingDelete(null);
      toast.error(message ?? "We couldn't remove that period.");
    },
  });

  const ready = name.trim().length > 0 && start.length > 0 && end.length > 0 && !add.isPending;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>School day</DialogTitle>
            <DialogDescription>
              The periods every lesson is placed on, in order. A break separates parts of the day
              and cannot hold a lesson.
            </DialogDescription>
          </DialogHeader>

          <ul className="divide-y rounded-lg border">
            {periods.map((period) => (
              <li key={period.id} className="flex items-center gap-3 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 font-medium">
                    {period.name}
                    {period.isBreak ? (
                      <span className="fn-eyebrow rounded-full bg-brass-soft px-2 py-0.5">
                        Break
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {period.startTime}–{period.endTime}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${period.name}`}
                  disabled={remove.isPending}
                  onClick={() => setPendingDelete(period)}
                >
                  <Trash2 className="size-4 text-destructive" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>

          <form
            className="space-y-3 rounded-lg border bg-muted/30 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (ready) add.mutate();
            }}
          >
            <p className="fn-eyebrow">Add a period</p>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="period-name">Name</Label>
                <Input
                  id="period-name"
                  value={name}
                  placeholder="P9"
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="period-start">Starts</Label>
                <Input
                  id="period-start"
                  type="time"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="period-end">Ends</Label>
                <Input
                  id="period-end"
                  type="time"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="period-is-break" checked={isBreak} onCheckedChange={setIsBreak} />
              <Label htmlFor="period-is-break" className="font-normal">
                This is a break, not a lesson period
              </Label>
            </div>
            <Button type="submit" size="sm" disabled={!ready}>
              <Plus className="size-4" aria-hidden="true" />
              {add.isPending ? "Adding…" : "Add period"}
            </Button>
          </form>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(next) => !next && setPendingDelete(null)}
        title={`Remove ${pendingDelete?.name ?? "this period"}?`}
        description="A period that still holds lessons cannot be removed. Move or remove its lessons first."
        confirmLabel="Remove period"
        destructive
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete)}
      />
    </>
  );
}
