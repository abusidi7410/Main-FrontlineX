import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { dateFmt } from "@/lib/format";
import { getAcademicStructure } from "@/services/academics.service";
import { deleteLessonPlan, getLessonPlans, saveLessonPlan } from "@/services/school.service";
import type { LessonPlan, LessonPlanInput } from "@/types";

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

const EMPTY: Omit<LessonPlanInput, "className" | "subject"> = {
  topic: "",
  durationMinutes: 40,
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
  const academics = useQuery({ queryKey: ["academics"], queryFn: getAcademicStructure });
  const [draft, setDraft] = useState<LessonPlanInput | null>(null);

  const save = useMutation({
    mutationFn: saveLessonPlan,
    onSuccess: async () => {
      toast.success("Lesson plan saved.");
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["lesson-plans"] });
    },
    onError: () => toast.error("We couldn't save this lesson plan. Please try again."),
  });

  const remove = useMutation({
    mutationFn: deleteLessonPlan,
    onSuccess: async () => {
      toast.success("Lesson plan deleted.");
      await queryClient.invalidateQueries({ queryKey: ["lesson-plans"] });
    },
    onError: () => toast.error("We couldn't delete this lesson plan. Please try again."),
  });

  const set = (key: keyof LessonPlanInput, value: string | number) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  const beginDraft = () => {
    if (!academics.data?.classes.length || !academics.data.subjects.length) return;
    setDraft({
      ...EMPTY,
      className: academics.data.classes[0]!,
      subject: academics.data.subjects[0]!,
    });
  };

  return (
    <PermissionGate permission="lessonplans.read">
      <div className="space-y-6">
        <PageHeader
          title="Lesson plans"
          description="Build plans against your school's classes, subjects and current term."
          actions={
            <IfAllowed permission="lessonplans.write">
              <Button
                className="h-11"
                onClick={beginDraft}
                disabled={academics.isPending || !academics.data?.classes.length}
              >
                New lesson plan
              </Button>
            </IfAllowed>
          }
        />

        {academics.isError ? (
          <ErrorState
            message="School classes and subjects could not be loaded. Retry before creating a lesson plan."
            onRetry={() => void academics.refetch()}
          />
        ) : null}

        {academics.data && !academics.data.classes.length ? (
          <p className="fn-panel p-5 text-sm text-muted-foreground">
            Add classes in Academic structure before creating lesson plans.
          </p>
        ) : null}

        {draft ? (
          <form
            className="fn-panel space-y-5 p-5"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(draft);
            }}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">
                  {draft.id ? "Edit lesson plan" : "New lesson plan"}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {academics.data?.session} · {academics.data?.term}
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField
                label="Subject"
                value={draft.subject}
                options={[...new Set([...(academics.data?.subjects ?? []), draft.subject])]}
                onChange={(value) => set("subject", value)}
              />
              <SelectField
                label="Class"
                value={draft.className}
                options={[...new Set([...(academics.data?.classes ?? []), draft.className])]}
                onChange={(value) => set("className", value)}
              />
              <TextField
                label="Topic"
                value={draft.topic}
                onChange={(value) => set("topic", value)}
              />
              <div className="space-y-1.5">
                <Label htmlFor="duration-minutes">Lesson duration (minutes)</Label>
                <Input
                  id="duration-minutes"
                  type="number"
                  min={1}
                  max={240}
                  step={1}
                  className="h-12"
                  required
                  value={draft.durationMinutes}
                  onChange={(event) => set("durationMinutes", Number(event.target.value))}
                />
              </div>
            </div>
            <AreaField
              label="Learning objectives"
              value={draft.objectives}
              onChange={(value) => set("objectives", value)}
              required
            />
            <AreaField
              label="Previous knowledge"
              value={draft.previousKnowledge}
              onChange={(value) => set("previousKnowledge", value)}
            />
            <AreaField
              label="Introduction"
              value={draft.introduction}
              onChange={(value) => set("introduction", value)}
            />
            <AreaField
              label="Teacher activities"
              value={draft.teacherActivities}
              onChange={(value) => set("teacherActivities", value)}
            />
            <AreaField
              label="Student activities"
              value={draft.studentActivities}
              onChange={(value) => set("studentActivities", value)}
            />
            <AreaField
              label="Instructional materials"
              value={draft.materials}
              onChange={(value) => set("materials", value)}
            />
            <AreaField
              label="Assessment"
              value={draft.assessment}
              onChange={(value) => set("assessment", value)}
            />
            <AreaField
              label="Homework"
              value={draft.homework}
              onChange={(value) => set("homework", value)}
            />
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                type="submit"
                className="h-12 text-base"
                disabled={
                  save.isPending ||
                  !draft.topic.trim() ||
                  !draft.subject ||
                  !draft.className ||
                  !draft.objectives.trim()
                }
              >
                {save.isPending ? "Saving…" : "Save lesson plan"}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-12"
                onClick={() => setDraft(null)}
                disabled={save.isPending}
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
        ) : query.data.length === 0 ? (
          <EmptyState
            title="No lesson plans yet"
            description="Create a plan for one of your school's classes and subjects. It will be saved with the current session and term."
            action={
              <IfAllowed permission="lessonplans.write">
                <Button onClick={beginDraft} disabled={academics.isPending || !academics.data}>
                  Create lesson plan
                </Button>
              </IfAllowed>
            }
          />
        ) : (
          <ul className="fn-panel divide-y">
            {query.data.map((plan) => (
              <LessonPlanRow
                key={plan.id}
                plan={plan}
                onEdit={() => setDraft({ ...plan })}
                onDelete={() => remove.mutate(plan.id)}
                deleting={remove.isPending && remove.variables === plan.id}
              />
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}

function LessonPlanRow({
  plan,
  onEdit,
  onDelete,
  deleting,
}: {
  plan: LessonPlan;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 p-4">
      <div className="min-w-0 flex-1">
        <p className="font-medium">{plan.topic}</p>
        <p className="text-sm text-muted-foreground">
          {plan.subject} · {plan.className} · {plan.session} · {plan.term} · {plan.durationMinutes}{" "}
          min
        </p>
        <p className="text-xs text-muted-foreground">Updated {dateFmt(plan.updatedAt)}</p>
      </div>
      <IfAllowed permission="lessonplans.write">
        <Button variant="outline" className="h-11" onClick={onEdit}>
          Edit
        </Button>
        <ConfirmDialog
          trigger={
            <Button variant="outline" className="h-11" disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          }
          title="Delete lesson plan?"
          description={`“${plan.topic}” will be removed from the school's lesson plans.`}
          confirmLabel="Delete plan"
          destructive
          onConfirm={onDelete}
        />
      </IfAllowed>
    </li>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="h-12">
          <SelectValue placeholder={`Choose ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
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
        required
      />
    </div>
  );
}

function AreaField({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        rows={3}
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
