import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { listPlatformSchools } from "@/services/platform.service";
import { transferStudent } from "@/services/students.service";
import type { PlatformSchool } from "@/types";

export function TransferStudentDialog({
  studentId,
  studentName,
  open,
  onOpenChange,
}: {
  studentId: string;
  studentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [schoolSearch, setSchoolSearch] = useState("");
  const [selectedSchoolId, setSelectedSchoolId] = useState<string | null>(null);

  const schoolsQuery = useQuery({
    queryKey: ["transfer-schools"],
    queryFn: () => listPlatformSchools(),
  });
  const transferSchools = (schoolsQuery.data ?? []).filter((school) => school.status === "active");
  const filteredSchools = transferSchools.filter(
    (school) =>
      !schoolSearch.trim() ||
      school.name.toLowerCase().includes(schoolSearch.trim().toLowerCase()) ||
      school.state.toLowerCase().includes(schoolSearch.trim().toLowerCase()),
  );
  const selectedSchool = transferSchools.find((school) => school.id === selectedSchoolId);

  const transfer = useMutation({
    mutationFn: (toSchoolId: string) => transferStudent({ studentId, toSchoolId }),
    onSuccess: async (student) => {
      toast.success(
        `${student.firstName} ${student.lastName} has been transferred to ${student.transferredTo?.schoolName ?? "the destination school"}.`,
      );
      setSelectedSchoolId(null);
      setSchoolSearch("");
      onOpenChange(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["student", studentId] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
      ]);
    },
    onError: () => toast.error("We couldn't complete the transfer. Please try again."),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Transfer {studentName} to another school</DialogTitle>
          <DialogDescription>
            Choose the destination school. The student&apos;s record moves there on the platform and
            their local status becomes &quot;Transferred&quot; — the receiving school accepts or
            rejects the transfer.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            className="h-11 pl-9"
            placeholder="Search destination schools by name or state"
            aria-label="Search destination schools"
            value={schoolSearch}
            onChange={(event) => setSchoolSearch(event.target.value)}
          />
        </div>

        <div className="max-h-72 space-y-2 overflow-y-auto pr-1" role="listbox">
          {schoolsQuery.isPending ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading schools…</p>
          ) : filteredSchools.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No active schools match your search.
            </p>
          ) : (
            filteredSchools.map((school) => (
              <SchoolOption
                key={school.id}
                school={school}
                selected={school.id === selectedSchoolId}
                onSelect={() => setSelectedSchoolId(school.id)}
              />
            ))
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => selectedSchool && transfer.mutate(selectedSchool.id)}
            disabled={!selectedSchool || transfer.isPending}
          >
            {transfer.isPending
              ? "Transferring…"
              : selectedSchool
                ? `Transfer to ${selectedSchool.name}`
                : "Select a school"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SchoolOption({
  school,
  selected,
  onSelect,
}: {
  school: PlatformSchool;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-xl border px-4 py-3 text-left transition-colors cursor-pointer",
        selected
          ? "border-primary/50 bg-primary/5 ring-1 ring-primary/30"
          : "border-input/70 bg-surface/50 hover:bg-accent/50",
      )}
    >
      <span className="min-w-0">
        <span className="block truncate font-medium">{school.name}</span>
        <span className="block text-sm text-muted-foreground">{school.state}</span>
      </span>
      <span
        className={cn(
          "size-4 shrink-0 rounded-full border-2 transition-colors",
          selected ? "border-primary bg-primary" : "border-input",
        )}
        aria-hidden="true"
      />
    </button>
  );
}
