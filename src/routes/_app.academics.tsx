import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { CalendarRange, Check, School, X } from "lucide-react";
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
import { ARMS } from "@/api/mock";
import {
  addClass,
  addSubject,
  getAcademicStructure,
  removeClass,
  removeSubject,
  TERM_OPTIONS,
  updateSessionTerm,
} from "@/services/academics.service";

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

  const query = useQuery({
    queryKey: ["academics"],
    queryFn: getAcademicStructure,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["academics"] });

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
    mutationFn: addClass,
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

          <section className="fn-panel p-5" aria-labelledby="subjects-heading">
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
