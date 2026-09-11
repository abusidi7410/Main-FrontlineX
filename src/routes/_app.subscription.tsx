import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { SUBSCRIPTION_TIERS, tierById } from "@/constants/plans";
import { dateFmt, naira, numberFmt, percent } from "@/lib/format";
import { getSubscription } from "@/services/school.service";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/subscription")({
  head: () => ({
    meta: [
      { title: "Subscription — Frontline Nexus" },
      {
        name: "description",
        content: "Your Frontline Nexus plan, student capacity, AI credits and renewal date.",
      },
      { property: "og:title", content: "Subscription — Frontline Nexus" },
      {
        property: "og:description",
        content: "Your plan, student capacity, AI credits and renewal date.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: SubscriptionPage,
});

function SubscriptionPage() {
  const query = useQuery({ queryKey: ["subscription"], queryFn: getSubscription });

  return (
    <PermissionGate permission="subscription.read">
      <div className="space-y-6">
        <PageHeader
          title="Subscription"
          description="Your plan is based on how many students are on roll. Capacity includes a growth allowance so mid-term admissions never block you."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          (() => {
            const sub = query.data;
            const tier = tierById(sub.tierId);
            const allowed = (tier.maxStudents ?? sub.activeStudents) + sub.growthAllowance;
            const usedPct = allowed ? (sub.activeStudents / allowed) * 100 : 0;
            const aiPct = sub.aiCreditsTotal ? (sub.aiCreditsUsed / sub.aiCreditsTotal) * 100 : 0;

            return (
              <>
                <div className="fn-panel flex flex-wrap items-center justify-between gap-4 p-5">
                  <div>
                    <p className="text-sm text-muted-foreground">Current plan</p>
                    <p className="font-display text-2xl font-semibold">{tier.label}</p>
                    <p className="text-sm text-muted-foreground">
                      {naira(tier.monthlyPrice)} / month · Renews {dateFmt(sub.renewalDate)} ·{" "}
                      {sub.paymentMethod ?? "No payment method saved"}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={sub.status} />
                    <Button>Manage billing</Button>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <StatCard
                    label="Students on roll"
                    value={`${numberFmt(sub.activeStudents)} / ${numberFmt(allowed)}`}
                    hint={`Includes a growth allowance of ${numberFmt(sub.growthAllowance)} students`}
                    tone={usedPct > 95 ? "warning" : "default"}
                  />
                  <StatCard
                    label="AI credits used"
                    value={`${numberFmt(sub.aiCreditsUsed)} / ${numberFmt(sub.aiCreditsTotal)}`}
                    hint={`${percent(aiPct)} of this month's allowance`}
                    tone={aiPct > 85 ? "warning" : "default"}
                  />
                  <StatCard
                    label="Storage used"
                    value={`${sub.storageUsedGb.toFixed(1)} GB / ${tier.storageGb} GB`}
                    hint="Documents, photos and result archives"
                  />
                </div>

                <section className="fn-panel space-y-4 p-5">
                  <h2 className="font-medium">Usage this billing cycle</h2>
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>Student capacity</span>
                        <span className="tabular-nums text-muted-foreground">
                          {percent(usedPct)}
                        </span>
                      </div>
                      <Progress value={Math.min(100, usedPct)} aria-label="Student capacity used" />
                    </div>
                    <div>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>AI credits</span>
                        <span className="tabular-nums text-muted-foreground">{percent(aiPct)}</span>
                      </div>
                      <Progress value={Math.min(100, aiPct)} aria-label="AI credits used" />
                    </div>
                  </div>
                </section>

                <section className="space-y-3">
                  <h2 className="font-medium">All plans</h2>
                  <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {SUBSCRIPTION_TIERS.map((t) => {
                      const current = t.id === tier.id;
                      return (
                        <li
                          key={t.id}
                          className={cn(
                            "fn-panel p-5",
                            current && "border-primary ring-1 ring-primary/30",
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-medium">{t.label}</p>
                            {current ? <StatusBadge status="active" /> : null}
                          </div>
                          <p className="mt-1 font-display text-xl font-semibold tabular-nums">
                            {naira(t.monthlyPrice)}
                            <span className="text-sm font-normal text-muted-foreground">
                              {" "}
                              /month
                            </span>
                          </p>
                          <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
                            <li className="flex gap-2">
                              <Check className="mt-0.5 size-4 text-success" aria-hidden="true" />
                              {numberFmt(t.aiCredits)} AI credits · {t.storageGb} GB storage
                            </li>
                            {t.features.map((f) => (
                              <li key={f} className="flex gap-2">
                                <Check className="mt-0.5 size-4 text-success" aria-hidden="true" />
                                {f}
                              </li>
                            ))}
                          </ul>
                          {!current ? (
                            <Button variant="outline" className="mt-4 w-full">
                              Switch to this plan
                            </Button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              </>
            );
          })()
        )}
      </div>
    </PermissionGate>
  );
}
