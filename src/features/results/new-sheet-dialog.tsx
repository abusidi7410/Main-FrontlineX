import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getAcademicStructure, TERM_OPTIONS } from "@/services/academics.service";
import { createResultSheet } from "@/services/school.service";

export function NewSheetDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const structureQuery = useQuery({
    queryKey: ["academics"],
    queryFn: getAcademicStructure,
  });
  const classes = structureQuery.data?.classes ?? [];
  const subjects = structureQuery.data?.subjects ?? [];

  const [className, setClassName] = useState("");
  const [subject, setSubject] = useState("");
  const [term, setTerm] = useState("");

  const create = useMutation({
    mutationFn: createResultSheet,
    onSuccess: async (sheet) => {
      toast.success(`${sheet.className} ${sheet.subject} sheet created. You can now enter scores.`);
      setClassName("");
      setSubject("");
      setTerm("");
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["results"] });
    },
    onError: (error) =>
      toast.error(
        error instanceof Error ? error.message : "We couldn't create that sheet. Please try again.",
      ),
  });

  const ready = className && subject && term;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New result sheet</DialogTitle>
          <DialogDescription>
            Create a draft sheet for a class and subject, then enter each student&apos;s marks.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="new-sheet-class">Class</Label>
            <Select value={className} onValueChange={setClassName}>
              <SelectTrigger id="new-sheet-class" className="h-11">
                <SelectValue placeholder="Select a class" />
              </SelectTrigger>
              <SelectContent>
                {classes.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-sheet-subject">Subject</Label>
            <Select value={subject} onValueChange={setSubject}>
              <SelectTrigger id="new-sheet-subject" className="h-11">
                <SelectValue placeholder="Select a subject" />
              </SelectTrigger>
              <SelectContent>
                {subjects.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-sheet-term">Term</Label>
            <Select value={term} onValueChange={setTerm}>
              <SelectTrigger id="new-sheet-term" className="h-11">
                <SelectValue placeholder="Select a term" />
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!ready || create.isPending}
            onClick={() => ready && create.mutate({ className, subject, term })}
          >
            {create.isPending ? "Creating…" : "Create sheet"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
