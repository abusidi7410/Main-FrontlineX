import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { numberFmt, percent } from "@/lib/format";
import {
  applyPromotion,
  getPromotionCandidates,
  listPromotionClasses,
  type PromotionDecision,
} from "@/services/promotion.service";

export const Route = createFileRoute("/_app/promotion")({
  head: () => ({
    meta: [
      { title: "Promotion centre — Frontline Nexus" },
      {
        name: "description",
        content: "Review promotion recommendations and move students to their next class.",
      },
      { property: "og:title", content: "Promotion centre — Frontline Nexus" },
      {
        property: "og:description",
        content: "Move students to their next class at the end of term.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PromotionPage,
});

const DECISION_LABELS: Record<PromotionDecision, string> = {
  promote: "Promote",
  repeat: "Repeat",
  review: "Review",
};

const DECISION_TONES: Record<PromotionDecision, string> = {
  promote: "bg-success-soft text-success border-success/25",
  repeat: "bg-destructive/10 text-destructive border-destructive/25",
  review: "bg-warning-soft text-warning border-warning/25",
};

function PromotionPage() {
  const queryClient = useQueryClient();
  const classesQuery = useQuery({
    queryKey: ["promotion-classes"],
    queryFn: listPromotionClasses,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, PromotionDecision>>({});

  const candidatesQuery = useQuery({
    queryKey: ["promotion-candidates", selected],
    queryFn: () => getPromotionCandidates(selected!),
    enabled: selected !== null,
  });

  useEffect(() => {
    if (candidatesQuery.data && Object.keys(decisions).length === 0) {
      const seed: Record<string, PromotionDecision> = {};
      for (const candidate of candidatesQuery.data) seed[candidate.studentId] = candidate.suggested;
      setDecisions(seed);
    }
  }, [candidatesQuery.data, decisions]);

  const apply = useMutation({
    mutationFn: () => applyPromotion(selected!, decisions),
    onSuccess: (result) => {
      toast.success(
        `${result.promoted} promoted · ${result.repeated} repeated · ${result.underReview} reviewed`,
      );
      void queryClient.invalidateQueries({ queryKey: ["promotion-classes"] });
      void queryClient.invalidateQueries({ queryKey: ["students"] });
      setSelected(null);
      setDecisions({});
    },
    onError: () => toast.error("We couldn't apply those promotions. Please try again."),
  });

  const candidates = candidatesQuery.data ?? [];
  const counts: Record<PromotionDecision, number> = { promote: 0, repeat: 0, review: 0 };
  for (const candidate of candidates) {
    counts[decisions[candidate.studentId] ?? candidate.suggested] += 1;
  }
  const touchable = selected !== null && candidates.length > 0 && !apply.isPending;

  return (
    <PermissionGate anyOf={["students.write", "academics.write"]}>
      <div className="space-y-6">
        <PageHeader
          title="Promotion centre"
          description="At the end of term, review each student's recommendation and move them to their next class in one batch."
        />

        {classesQuery.isError ? (
          <ErrorState onRetry={() => void classesQuery.refetch()} />
        ) : classesQuery.isPending ? (
          <ListSkeleton />
        ) : selected === null ? (
          <>
            <p className="text-sm text-muted-foreground">
              Choose a class to see every active student and the recommendation your school policy
              produces for them.
            </p>
            <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {classesQuery.data.map((group) => (
                <li key={group.className}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelected(group.className);
                      setDecisions({});
                    }}
                    className="fn-panel w-full text-left transition-colors hover:border-primary/40"
                  >
                    <span className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-4">
                      <span className="font-semibold">{group.className}</span>
                      <span className="text-sm text-muted-foreground">
                        → {group.nextClass ?? "Graduation"}
                      </span>
                    </span>
                    <span className="grid grid-cols-4 divide-x">
                      <span className="px-4 py-3">
                        <span className="block text-lg font-semibold">
                          {numberFmt(group.total)}
                        </span>
                        <span className="text-xs text-muted-foreground">Students</span>
                      </span>
                      <span className="px-4 py-3">
                        <span className="block text-lg font-semibold text-success">
                          {numberFmt(group.promote)}
                        </span>
                        <span className="text-xs text-muted-foreground">Promote</span>
                      </span>
                      <span className="px-4 py-3">
                        <span className="block text-lg font-semibold text-warning">
                          {numberFmt(group.review)}
                        </span>
                        <span className="text-xs text-muted-foreground">Review</span>
                      </span>
                      <span className="px-4 py-3">
                        <span className="block text-lg font-semibold text-destructive">
                          {numberFmt(group.repeat)}
                        </span>
                        <span className="text-xs text-muted-foreground">Repeat</span>
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="px-2"
                  onClick={() => {
                    setSelected(null);
                    setDecisions({});
                  }}
                >
                  <ArrowLeft className="size-4" aria-hidden="true" />
                  All classes
                </Button>
                <h2 className="font-display text-xl font-semibold">{selected}</h2>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge className={DECISION_TONES.promote}>{counts.promote} promote</Badge>
                <Badge className={DECISION_TONES.review}>{counts.review} review</Badge>
                <Badge className={DECISION_TONES.repeat}>{counts.repeat} repeat</Badge>
              </div>
            </div>

            {candidatesQuery.isError ? (
              <ErrorState onRetry={() => void candidatesQuery.refetch()} />
            ) : candidatesQuery.isPending ? (
              <ListSkeleton />
            ) : candidates.length === 0 ? (
              <p className="fn-panel p-5 text-sm text-muted-foreground">
                No active students in this class.
              </p>
            ) : (
              <div className="fn-panel overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[42rem] text-left">
                    <caption className="sr-only">Promotion decisions for {selected}</caption>
                    <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                      <tr>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Student
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Average
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Attendance
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Recommendation
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Decision
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {candidates.map((candidate) => {
                        const decision = decisions[candidate.studentId] ?? candidate.suggested;
                        return (
                          <tr key={candidate.studentId}>
                            <td className="px-4 py-3">
                              <p className="font-medium">{candidate.studentName}</p>
                              <p className="text-sm text-muted-foreground">
                                {candidate.admissionNumber}
                              </p>
                            </td>
                            <td className="px-4 py-3 tabular-nums">
                              <span
                                className={
                                  candidate.average >= 60
                                    ? "font-medium text-success"
                                    : candidate.average >= 45
                                      ? "font-medium text-warning"
                                      : "font-medium text-destructive"
                                }
                              >
                                {candidate.average}%
                              </span>
                            </td>
                            <td className="px-4 py-3 tabular-nums">
                              {percent(candidate.attendanceRate)}
                            </td>
                            <td className="px-4 py-3">
                              <Badge className={DECISION_TONES[candidate.suggested]}>
                                {DECISION_LABELS[candidate.suggested]}
                              </Badge>
                            </td>
                            <td className="px-4 py-3">
                              <Select
                                value={decision}
                                onValueChange={(value) =>
                                  setDecisions((prev) => ({
                                    ...prev,
                                    [candidate.studentId]: value as PromotionDecision,
                                  }))
                                }
                              >
                                <SelectTrigger className="h-10 w-36">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {(Object.keys(DECISION_LABELS) as PromotionDecision[]).map(
                                    (option) => (
                                      <SelectItem key={option} value={option}>
                                        {DECISION_LABELS[option]}
                                      </SelectItem>
                                    ),
                                  )}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/30 px-5 py-4">
                  <p className="text-sm text-muted-foreground">
                    {counts.promote} of {numberFmt(candidates.length)} students will move up (
                    {DECISION_LABELS.promote.toLowerCase()}) and {counts.repeat} will repeat the
                    class.
                  </p>
                  <ConfirmDialog
                    trigger={
                      <Button disabled={!touchable}>
                        {apply.isPending
                          ? "Applying…"
                          : counts.promote > 0
                            ? `Promote ${counts.promote} students`
                            : "Apply decisions"}
                      </Button>
                    }
                    title={`Apply promotion decisions for ${selected}`}
                    description="This updates each student's class and records the outcome in their enrolment history. Students marked “promote” move to the next class; the final class graduates."
                    confirmLabel="Apply"
                    onConfirm={() => apply.mutate()}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </PermissionGate>
  );
}
