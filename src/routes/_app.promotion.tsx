import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { useAuthenticatedSession } from "@/auth/session";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { numberFmt, percent } from "@/lib/format";
import {
  applyPromotion,
  getPromotionCandidates,
  listPromotionClasses,
  updatePromotionPolicy,
  type PromotionCandidate,
  type PromotionDecision,
  type PromotionPolicy,
} from "@/services/promotion.service";
import { invalidateEnrollmentQueries } from "@/lib/query-invalidation";

export const Route = createFileRoute("/_app/promotion")({
  head: () => ({
    meta: [
      { title: "Promotion centre — Frontline Nexus" },
      {
        name: "description",
        content: "Review published results and attendance before approving student progression.",
      },
      { property: "og:title", content: "Promotion centre — Frontline Nexus" },
      {
        property: "og:description",
        content:
          "Review each student's academic record before applying session promotion decisions.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PromotionPage,
});

const DECISION_LABELS: Record<PromotionDecision, string> = {
  promote: "Promote",
  conditional: "Promote with conditions",
  repeat: "Repeat",
  review: "Review",
};

const DECISION_TONES: Record<PromotionDecision, string> = {
  promote: "bg-success-soft text-success border-success/25",
  conditional: "bg-warning-soft text-warning border-warning/25",
  repeat: "bg-destructive/10 text-destructive border-destructive/25",
  review: "bg-muted text-muted-foreground border-border",
};

const POLICY_FIELDS: {
  key: keyof PromotionPolicy;
  label: string;
  max: number;
  step: string;
}[] = [
  { key: "promoteMinAverage", label: "Promotion average (%)", max: 100, step: "0.1" },
  { key: "promoteMinAttendance", label: "Promotion attendance (%)", max: 100, step: "0.1" },
  { key: "conditionalMinAverage", label: "Conditional average (%)", max: 100, step: "0.1" },
  {
    key: "conditionalMinAttendance",
    label: "Conditional attendance (%)",
    max: 100,
    step: "0.1",
  },
  {
    key: "conditionalMaxFailedSubjects",
    label: "Maximum failed subjects for conditions",
    max: 20,
    step: "1",
  },
];

function PromotionPage() {
  const queryClient = useQueryClient();
  const { user } = useAuthenticatedSession();
  const canApply =
    user.permissions.includes("students.write") && user.permissions.includes("academics.write");
  const canManagePolicy = user.permissions.includes("academics.write");
  const classesQuery = useQuery({
    queryKey: ["promotion-classes"],
    queryFn: listPromotionClasses,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, PromotionDecision>>({});
  const [policyDraft, setPolicyDraft] = useState<PromotionPolicy | null>(null);
  const [confirmDecisions, setConfirmDecisions] = useState<Record<
    string,
    PromotionDecision
  > | null>(null);

  const candidatesQuery = useQuery({
    queryKey: ["promotion-candidates", selected],
    queryFn: () => getPromotionCandidates(selected!),
    enabled: selected !== null,
  });

  useEffect(() => {
    if (!policyDraft && classesQuery.data) setPolicyDraft(classesQuery.data.policy);
  }, [classesQuery.data, policyDraft]);

  useEffect(() => {
    if (candidatesQuery.data && Object.keys(decisions).length === 0) {
      const seed: Record<string, PromotionDecision> = {};
      for (const candidate of candidatesQuery.data.candidates) {
        seed[candidate.studentId] = candidate.suggested;
      }
      setDecisions(seed);
    }
  }, [candidatesQuery.data, decisions]);

  const apply = useMutation({
    mutationFn: (input: { className: string; decisions: Record<string, PromotionDecision> }) =>
      applyPromotion(input.className, input.decisions),
    onSuccess: async (result) => {
      toast.success(
        `${result.promoted} promoted · ${result.conditional} conditional · ${result.repeated} repeated · ${result.graduated} graduated · ${result.underReview} reviewed`,
      );
      setSelected(null);
      setDecisions({});
      setConfirmDecisions(null);
      await invalidateEnrollmentQueries(queryClient);
    },
    onError: () => toast.error("We couldn't apply those promotions. Please reload and try again."),
  });

  const savePolicy = useMutation({
    mutationFn: updatePromotionPolicy,
    onSuccess: async (policy) => {
      toast.success("Promotion policy updated.");
      setPolicyDraft(policy);
      await invalidateEnrollmentQueries(queryClient);
    },
    onError: () =>
      toast.error("We couldn't save the promotion policy. Please check the thresholds."),
  });

  const candidates = useMemo(() => candidatesQuery.data?.candidates ?? [], [candidatesQuery.data]);
  const counts = useMemo(() => {
    const result: Record<PromotionDecision, number> = {
      promote: 0,
      conditional: 0,
      repeat: 0,
      review: 0,
    };
    for (const candidate of candidates) {
      result[decisions[candidate.studentId] ?? candidate.suggested] += 1;
    }
    return result;
  }, [candidates, decisions]);
  const touchable = canApply && selected !== null && candidates.length > 0 && !apply.isPending;
  const finalClass = candidatesQuery.data?.nextClass === null && candidates.length > 0;
  const applyCurrentDecisions = () => setConfirmDecisions({ ...decisions });
  const approveAllEligible = () => {
    const eligible: Record<string, PromotionDecision> = {};
    for (const candidate of candidates) {
      eligible[candidate.studentId] = candidate.suggested === "promote" ? "promote" : "review";
    }
    setConfirmDecisions(eligible);
  };

  return (
    <PermissionGate permission="academics.read">
      <div className="space-y-6">
        <PageHeader
          title="Promotion centre"
          description="Use published results and session attendance to guide decisions. Recommendations never change enrolments until an authorised administrator approves them."
        />

        {classesQuery.isError ? (
          <ErrorState onRetry={() => void classesQuery.refetch()} />
        ) : classesQuery.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <section className="fn-panel space-y-4 p-5" aria-labelledby="policy-heading">
              <div>
                <h2 id="policy-heading" className="font-semibold">
                  School promotion policy
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Missing published results or attendance always requires review. Conditional
                  promotion is recorded in the next-session enrolment.
                </p>
              </div>
              <form
                className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (policyDraft) savePolicy.mutate(policyDraft);
                }}
              >
                {POLICY_FIELDS.map((field) => (
                  <div key={field.key} className="space-y-1.5">
                    <Label htmlFor={`policy-${field.key}`}>{field.label}</Label>
                    <Input
                      id={`policy-${field.key}`}
                      type="number"
                      min={0}
                      max={field.max}
                      step={field.step}
                      required
                      disabled={!canManagePolicy}
                      value={policyDraft?.[field.key] ?? ""}
                      onChange={(event) =>
                        setPolicyDraft((current) =>
                          current
                            ? { ...current, [field.key]: Number(event.target.value) }
                            : current,
                        )
                      }
                    />
                  </div>
                ))}
                <IfAllowed permission="academics.write">
                  <div className="flex items-end">
                    <Button
                      type="submit"
                      variant="outline"
                      disabled={!policyDraft || savePolicy.isPending}
                    >
                      {savePolicy.isPending ? "Saving…" : "Save policy"}
                    </Button>
                  </div>
                </IfAllowed>
              </form>
              {policyDraft ? (
                <p className="text-xs text-muted-foreground">
                  Promote at {policyDraft.promoteMinAverage}% average and{" "}
                  {policyDraft.promoteMinAttendance}% attendance with no failed subjects.
                  Conditional promotion requires at least {policyDraft.conditionalMinAverage}%
                  average, {policyDraft.conditionalMinAttendance}% attendance, and no more than{" "}
                  {policyDraft.conditionalMaxFailedSubjects} failed subjects.
                </p>
              ) : null}
            </section>

            <p className="text-sm text-muted-foreground">
              Reviewing {classesQuery.data.sourceSession}; approved outcomes are recorded in{" "}
              {classesQuery.data.targetSession}. Review decisions leave the student's current
              enrolment unchanged.
            </p>

            {selected === null ? (
              classesQuery.data.classes.length === 0 ? (
                <EmptyState
                  title="No active classes"
                  description="Set up classes and enroll students in Academic structure before preparing promotions."
                />
              ) : (
                <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {classesQuery.data.classes.map((group) => (
                    <li key={group.className}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(group.className);
                          setDecisions({});
                        }}
                        disabled={group.total === 0}
                        className="fn-panel w-full text-left transition-colors hover:border-primary/40 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <span className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-4">
                          <span className="font-semibold">{group.className}</span>
                          <span className="text-sm text-muted-foreground">
                            {group.nextClass ? `→ ${group.nextClass}` : "Final class · graduation"}
                          </span>
                        </span>
                        <span className="grid grid-cols-2 divide-x sm:grid-cols-5">
                          <SummaryCount label="Students" value={group.total} />
                          <SummaryCount
                            label={group.nextClass ? "Promote" : "Graduate"}
                            value={group.promote}
                            tone="text-success"
                          />
                          <SummaryCount
                            label="Conditional"
                            value={group.conditional}
                            tone="text-warning"
                          />
                          <SummaryCount
                            label="Repeat"
                            value={group.repeat}
                            tone="text-destructive"
                          />
                          <SummaryCount label="Review" value={group.review} />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )
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
                    <p className="text-sm text-muted-foreground">
                      {candidatesQuery.data?.sourceSession} → {candidatesQuery.data?.targetSession}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge className={DECISION_TONES.promote}>
                      {counts.promote} {finalClass ? "graduate" : "promote"}
                    </Badge>
                    {!finalClass ? (
                      <Badge className={DECISION_TONES.conditional}>
                        {counts.conditional} conditional
                      </Badge>
                    ) : null}
                    <Badge className={DECISION_TONES.repeat}>{counts.repeat} repeat</Badge>
                    <Badge className={DECISION_TONES.review}>{counts.review} review</Badge>
                  </div>
                </div>

                {candidatesQuery.isError ? (
                  <ErrorState onRetry={() => void candidatesQuery.refetch()} />
                ) : candidatesQuery.isPending ? (
                  <ListSkeleton />
                ) : candidates.length === 0 ? (
                  <EmptyState
                    title="No active students in this class"
                    description="Only currently enrolled students are included in promotion review."
                  />
                ) : (
                  <div className="fn-panel overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[55rem] text-left">
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
                              Failed subjects
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
                          {candidates.map((candidate) => (
                            <PromotionRow
                              key={candidate.studentId}
                              candidate={candidate}
                              decision={decisions[candidate.studentId] ?? candidate.suggested}
                              onDecision={(decision) =>
                                setDecisions((previous) => ({
                                  ...previous,
                                  [candidate.studentId]: decision,
                                }))
                              }
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/30 px-5 py-4">
                      <p className="text-sm text-muted-foreground">
                        {counts.promote} {finalClass ? "graduate" : "promote"} ·{" "}
                        {counts.conditional} conditional · {counts.repeat} repeat · {counts.review}{" "}
                        review. Review leaves current enrolments unchanged.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {canApply ? (
                          <Button
                            variant="outline"
                            disabled={
                              !touchable ||
                              !candidates.some((candidate) => candidate.suggested === "promote")
                            }
                            onClick={approveAllEligible}
                          >
                            Approve all eligible
                          </Button>
                        ) : null}
                        <IfAllowed permission="academics.write">
                          <Button disabled={!touchable} onClick={applyCurrentDecisions}>
                            {apply.isPending
                              ? "Applying…"
                              : finalClass && counts.promote > 0
                                ? `Approve ${counts.promote} graduations`
                                : `Apply ${numberFmt(candidates.length)} decisions`}
                          </Button>
                        </IfAllowed>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {selected ? (
          <ConfirmDialog
            open={confirmDecisions !== null}
            onOpenChange={(open) => {
              if (!open) setConfirmDecisions(null);
            }}
            title={`Apply promotion decisions for ${selected}`}
            description={`Outcomes will be recorded for the ${classesQuery.data?.sourceSession} session and destination ${classesQuery.data?.targetSession}. Students marked “Review” remain in their current enrolment.`}
            confirmLabel="Apply decisions"
            onConfirm={() => {
              if (confirmDecisions) {
                apply.mutate({ className: selected, decisions: confirmDecisions });
              }
            }}
          />
        ) : null}
      </div>
    </PermissionGate>
  );
}

function SummaryCount({
  label,
  value,
  tone = "text-foreground",
}: {
  label: string;
  value: number;
  tone?: string;
}) {
  return (
    <span className="min-w-0 px-4 py-3">
      <span className={`block text-lg font-semibold ${tone}`}>{numberFmt(value)}</span>
      <span className="block truncate text-xs text-muted-foreground">{label}</span>
    </span>
  );
}

function PromotionRow({
  candidate,
  decision,
  onDecision,
}: {
  candidate: PromotionCandidate;
  decision: PromotionDecision;
  onDecision: (decision: PromotionDecision) => void;
}) {
  const options: PromotionDecision[] = candidate.isFinalClass
    ? ["promote", "repeat", "review"]
    : ["promote", "conditional", "repeat", "review"];
  const recommendation =
    candidate.isFinalClass && candidate.suggested === "promote"
      ? "Graduate"
      : DECISION_LABELS[candidate.suggested];
  return (
    <tr>
      <td className="px-4 py-3">
        <p className="font-medium">{candidate.studentName}</p>
        <p className="text-sm text-muted-foreground">{candidate.admissionNumber}</p>
      </td>
      <td className="px-4 py-3 tabular-nums">
        {candidate.average === null ? "—" : `${candidate.average}%`}
        <p className="text-xs text-muted-foreground">
          {candidate.subjectsAssessed} subject{candidate.subjectsAssessed === 1 ? "" : "s"}
        </p>
      </td>
      <td className="px-4 py-3 tabular-nums">{candidate.failedSubjects}</td>
      <td className="px-4 py-3 tabular-nums">
        {candidate.attendanceRate === null ? "—" : percent(candidate.attendanceRate)}
        <p className="text-xs text-muted-foreground">
          {numberFmt(candidate.attendanceRecords)} recorded days
        </p>
      </td>
      <td className="px-4 py-3">
        <Badge className={DECISION_TONES[candidate.suggested]}>{recommendation}</Badge>
        <p className="mt-1 max-w-48 text-xs text-muted-foreground">{candidate.reason}</p>
      </td>
      <td className="px-4 py-3">
        <Select value={decision} onValueChange={(value) => onDecision(value as PromotionDecision)}>
          <SelectTrigger className="h-10 w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option} value={option}>
                {candidate.isFinalClass && option === "promote"
                  ? "Graduate"
                  : DECISION_LABELS[option]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
    </tr>
  );
}
