import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
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
import { updateResultSheetScores } from "@/services/school.service";
import type { ResultSheet, ResultSheetRow } from "@/types";

const LIMITS: Record<"ca1" | "ca2" | "assignment" | "exam", number> = {
  ca1: 10,
  ca2: 10,
  assignment: 20,
  exam: 60,
};

const COMPONENTS: Array<{ key: "ca1" | "ca2" | "assignment" | "exam"; label: string }> = [
  { key: "ca1", label: "CA 1" },
  { key: "ca2", label: "CA 2" },
  { key: "assignment", label: "Assignment" },
  { key: "exam", label: "Exam" },
];

function totalOf(row: ResultSheetRow) {
  return (row.ca1 ?? 0) + (row.ca2 ?? 0) + (row.assignment ?? 0) + (row.exam ?? 0);
}

export function ScoresDialog({
  sheet,
  open,
  onOpenChange,
}: {
  sheet: ResultSheet | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<ResultSheetRow[]>([]);

  useEffect(() => {
    if (sheet) setRows(sheet.rows.map((row) => ({ ...row })));
  }, [sheet]);

  const save = useMutation({
    mutationFn: (next: ResultSheetRow[]) => updateResultSheetScores(sheet?.id ?? "", next),
    onSuccess: async (updated) => {
      toast.success(`Scores saved for ${updated.className} ${updated.subject}.`);
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["results"] });
    },
    onError: () => toast.error("We couldn't save those scores. Please try again."),
  });

  if (!sheet) return null;

  const setScore = (studentId: string, key: "ca1" | "ca2" | "assignment" | "exam", raw: string) => {
    const value = raw.trim() === "" ? null : Math.max(0, Math.min(LIMITS[key], Number(raw)));
    setRows((prev) =>
      prev.map((row) => (row.studentId === studentId ? { ...row, [key]: value } : row)),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            Enter scores · {sheet.className} {sheet.subject}
          </DialogTitle>
          <DialogDescription>
            Type each student&apos;s marks. CA 1 and CA 2 are out of 10, the assignment out of 20,
            and the exam out of 60.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-96 overflow-y-auto rounded-xl border">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="sticky top-0 border-b bg-muted/40 text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  Student
                </th>
                {COMPONENTS.map((component) => (
                  <th
                    key={component.key}
                    scope="col"
                    className="w-24 px-3 py-3 text-center font-medium"
                  >
                    {component.label}
                  </th>
                ))}
                <th scope="col" className="w-24 px-3 py-3 text-center font-medium">
                  Total
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-muted-foreground" colSpan={6}>
                    No students are enrolled in {sheet.className} yet.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.studentId}>
                    <td className="px-4 py-2 font-medium">{row.studentName}</td>
                    {COMPONENTS.map((component) => (
                      <td key={component.key} className="px-3 py-2">
                        <Input
                          type="number"
                          inputMode="numeric"
                          min={0}
                          max={LIMITS[component.key]}
                          className="h-9 text-center tabular-nums"
                          aria-label={`${row.studentName} ${component.label}`}
                          value={row[component.key] ?? ""}
                          onChange={(event) =>
                            setScore(row.studentId, component.key, event.target.value)
                          }
                        />
                      </td>
                    ))}
                    <td className="px-3 py-2 text-center font-semibold tabular-nums">
                      {totalOf(row)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={save.isPending || rows.length === 0} onClick={() => save.mutate(rows)}>
            {save.isPending ? "Saving…" : "Save scores"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
