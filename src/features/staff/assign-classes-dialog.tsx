import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ARMS, CLASSES } from "@/constants/reference";
import type { StaffMember } from "@/types";

export const CLASS_OPTIONS = CLASSES.flatMap((className) =>
  ARMS.map((arm) => ({ className, arm, value: `${className}${arm}` })),
);

export function AssignClassesDialog({
  member,
  open,
  onOpenChange,
  isPending,
  onAssign,
}: {
  member: StaffMember | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPending: boolean;
  onAssign: (classes: string[]) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (member) setSelected(new Set(member.classes));
  }, [member]);

  const toggle = (value: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(value);
      else next.delete(value);
      return next;
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Assign classes</DialogTitle>
          <DialogDescription>
            Pick which classes {member?.fullName ?? "this staff member"} teaches. Their class
            assignments will update across the roster.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {CLASS_OPTIONS.map((option) => {
            const checked = selected.has(option.value);
            return (
              <Label
                key={option.value}
                htmlFor={`class-${option.value.replace(/\s+/g, "-")}`}
                className="flex cursor-pointer items-center gap-3 rounded-lg border border-input/70 bg-surface/50 px-3 py-2 transition-colors has-[[data-state=checked]]:border-primary/40 has-[[data-state=checked]]:bg-primary/5 hover:bg-accent/40"
              >
                <Checkbox
                  id={`class-${option.value.replace(/\s+/g, "-")}`}
                  checked={checked}
                  onCheckedChange={(next) => toggle(option.value, next === true)}
                />
                <span className="text-sm font-medium">{option.value}</span>
              </Label>
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => onAssign(Array.from(selected).sort())} disabled={isPending}>
            {isPending ? "Saving…" : "Save classes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
