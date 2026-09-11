import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { dateFmt } from "@/lib/format";
import { getLessonPlans, saveLessonPlan } from "@/services/school.service";
import type { LessonPlan } from "@/types";

export const Route = createFileRoute("/_app/lesson-plans")({
  head: () => ({
    meta: [
      { title: "Lesson plans — Frontline Nexus" },
      {
        name: "description",
        content: "Write, save and reuse structured lesson plans built for the Nigerian curriculum.",
      },
      { property: "og:title", content: "Lesson plans — Frontline Nexus" },
      { property: "og:description", content: "Write, save and reuse structured lesson plans." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: LessonPlansPage,
});

const EMPTY: Omit<LessonPlan, "id" | "updatedAt"> = {
  subject: "",
  className: "",
  topic: "",
  duration: "40 minutes",
  objectives: "",
  previousKnowledge: "",
  introduction: "",
  teacherActivities: "",
  studentActivities: "",
  materials: "",
  assessment: "",
  homework: "",
};

function LessonPlansPage() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["lesson-plans"], queryFn: getLessonPlans });
  const [draft, setDraft] = useState<
    (Omit<LessonPlan, "id" | "updatedAt"> & { id?: string }) | null
  >(null);

  const save = useMutation({
    mutationFn: saveLessonPlan,
    onSuccess: async () => {
      toast.success("Lesson plan saved.");
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["lesson-plans"] });
    },
    onError: () => toast.error("We couldn't save this lesson plan. Please try again."),
  });

  const set = (key: keyof typeof EMPTY, value: string) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  return (
    <PermissionGate permission="lessonplans.read">
      <div className="space-y-6">
        <PageHeader
          title="Lesson plans"
          description="Structured plans with objectives, activities, materials and assessment — ready for inspection."
          actions={
            <Button className="h-11" onClick={() => setDraft({ ...EMPTY })}>
              New lesson plan
            </Button>
          }
        />

        {draft ? (
          <form
            className="fn-panel space-y-4 p-5"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(draft);
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField
                label="Subject"
                value={draft.subject}
                onChange={(v) => set("subject", v)}
              />
              <TextField
                label="Class"
                value={draft.className}
                onChange={(v) => set("className", v)}
              />
              <TextField label="Topic" value={draft.topic} onChange={(v) => set("topic", v)} />
              <TextField
                label="Duration"
                value={draft.duration}
                onChange={(v) => set("duration", v)}
              />
            </div>
            <AreaField
              label="Learning objectives"
              value={draft.objectives}
              onChange={(v) => set("objectives", v)}
            />
            <AreaField
              label="Previous knowledge"
              value={draft.previousKnowledge}
              onChange={(v) => set("previousKnowledge", v)}
            />
            <AreaField
              label="Introduction"
              value={draft.introduction}
              onChange={(v) => set("introduction", v)}
            />
            <AreaField
              label="Teacher activities"
              value={draft.teacherActivities}
              onChange={(v) => set("teacherActivities", v)}
            />
            <AreaField
              label="Student activities"
              value={draft.studentActivities}
              onChange={(v) => set("studentActivities", v)}
            />
            <AreaField
              label="Instructional materials"
              value={draft.materials}
              onChange={(v) => set("materials", v)}
            />
            <AreaField
              label="Assessment"
              value={draft.assessment}
              onChange={(v) => set("assessment", v)}
            />
            <AreaField
              label="Homework"
              value={draft.homework}
              onChange={(v) => set("homework", v)}
            />
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="submit" className="h-12 text-base" disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save lesson plan"}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-12"
                onClick={() => setDraft(null)}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : null}

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <ul className="fn-panel divide-y">
            {query.data.map((plan) => (
              <li key={plan.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{plan.topic}</p>
                  <p className="text-sm text-muted-foreground">
                    {plan.subject} · {plan.className} · updated {dateFmt(plan.updatedAt)}
                  </p>
                </div>
                <Button variant="outline" className="h-11" onClick={() => setDraft({ ...plan })}>
                  Edit
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        className="h-12"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function AreaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} rows={3} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}
