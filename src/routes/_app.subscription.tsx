import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { tierById } from "@/constants/plans";
import { dateFmt, naira, numberFmt, percent } from "@/lib/format";
import {
  getSubscription,
  getSubscriptionPlans,
  startSubscriptionCheckout,
  verifySubscriptionPayment,
} from "@/services/school.service";
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
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["subscription"], queryFn: getSubscription });
  const plansQuery = useQuery({ queryKey: ["subscriptionPlans"], queryFn: getSubscriptionPlans });
  const processedReference = useRef<string | null>(null);
  const [reference, setReference] = useState<string | null>(null);
  const [checkoutPlanId, setCheckoutPlanId] = useState<string | null>(null);
  const [verification, setVerification] = useState<
    "verifying" | "success" | "pending" | "failed" | "error" | null
  >(null);

  const verifyReturn = async (paymentReference: string) => {
    setVerification("verifying");
    try {
      const result = await verifySubscriptionPayment(paymentReference);
      setVerification(result.status);
      if (result.status === "success") {
        await queryClient.invalidateQueries({ queryKey: ["subscription"] });
        toast.success("Payment confirmed. Your subscription is active.");
      } else if (result.status === "pending") {
        toast.error("Payment is not confirmed yet. You can retry verification shortly.");
      } else {
        toast.error("The payment was not completed. Your subscription was not changed.");
      }
    } catch (error) {
      setVerification("error");
      toast.error(
        error instanceof Error
          ? error.message
          : "We couldn't verify the payment. Please try again.",
      );
    }
  };

  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const returnedReference = search.get("reference") ?? search.get("trxref");
    if (returnedReference) setReference(returnedReference);
  }, []);

  useEffect(() => {
    if (!reference || processedReference.current === reference) return;
    processedReference.current = reference;
    void verifyReturn(reference);
    // Verify once when Paystack returns; retries are user-triggered below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reference]);

  const beginCheckout = async (planId: string) => {
    setCheckoutPlanId(planId);
    try {
      const checkout = await startSubscriptionCheckout(planId);
      const destination = new URL(checkout.authorizationUrl);
      if (destination.protocol !== "https:" || destination.hostname !== "checkout.paystack.com") {
        throw new Error("Paystack returned an invalid checkout address.");
      }
      window.location.assign(destination.href);
    } catch (error) {
      setCheckoutPlanId(null);
      toast.error(
        error instanceof Error ? error.message : "We couldn't start checkout. Please try again.",
      );
    }
  };

  return (
    <PermissionGate permission="subscription.read">
      <div className="space-y-6">
        <PageHeader
          title="Subscription"
          description="Your plan is based on how many students are on roll. Capacity includes a growth allowance so mid-term admissions never block you."
        />

        {verification ? (
          <div className="fn-panel space-y-3 p-4" role="status" aria-live="polite">
            <p>
              {verification === "verifying" && "Checking your payment with Paystack…"}
              {verification === "success" && "Payment confirmed. Your subscription is active."}
              {verification === "pending" &&
                "Payment is not confirmed yet. If you completed checkout, try verifying again."}
              {verification === "failed" &&
                "Payment was not completed. Your subscription has not changed."}
              {verification === "error" &&
                "We couldn't confirm the payment right now. You can safely retry verification."}
            </p>
            {reference && ["pending", "error"].includes(verification) ? (
              <Button
                variant="outline"
                disabled={verification === "verifying"}
                onClick={() => void verifyReturn(reference)}
              >
                {verification === "verifying" ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : null}
                Verify payment again
              </Button>
            ) : null}
          </div>
        ) : null}

        {query.isError || plansQuery.isError ? (
          <ErrorState
            onRetry={() => {
              void query.refetch();
              void plansQuery.refetch();
            }}
          />
        ) : query.isPending || plansQuery.isPending ? (
          <ListSkeleton />
        ) : (
          (() => {
            const sub = query.data;
            const plans = plansQuery.data;
            const tier = plans.find((plan) => plan.id === sub.tierId) ?? tierById(sub.tierId);
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
                    <Button
                      disabled={checkoutPlanId !== null}
                      onClick={() => void beginCheckout(tier.id)}
                    >
                      {checkoutPlanId === tier.id ? (
                        <Loader2 className="animate-spin" aria-hidden="true" />
                      ) : null}
                      {checkoutPlanId === tier.id ? "Opening checkout…" : "Renew subscription"}
                    </Button>
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
                    {plans.map((t) => {
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
                            <Button
                              variant="outline"
                              className="mt-4 w-full"
                              disabled={checkoutPlanId !== null}
                              onClick={() => void beginCheckout(t.id)}
                            >
                              {checkoutPlanId === t.id ? (
                                <Loader2 className="animate-spin" aria-hidden="true" />
                              ) : null}
                              {checkoutPlanId === t.id
                                ? "Opening checkout…"
                                : "Switch to this plan"}
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
