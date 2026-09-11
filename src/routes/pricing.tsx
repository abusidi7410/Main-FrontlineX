import { createFileRoute, Link } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BrandLockup } from "@/components/layout/brand";
import { SUBSCRIPTION_TIERS } from "@/constants/plans";
import { naira, numberFmt } from "@/lib/format";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — Frontline Nexus School Management" },
      {
        name: "description",
        content:
          "Student-based monthly pricing for Frontline Nexus. Every plan includes AI credits, parent portal, offline teacher app and unlimited staff accounts.",
      },
      { property: "og:title", content: "Frontline Nexus pricing" },
      {
        property: "og:description",
        content:
          "Transparent student-based tiers from ₦8,000/month, with AI credits and storage included.",
      },
    ],
  }),
  component: PricingPage,
});

function PricingPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-surface/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" aria-label="Frontline Nexus home">
            <BrandLockup />
          </Link>
          <Button asChild>
            <Link to="/get-started">Create your school</Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="fn-grid-bg relative overflow-hidden rounded-3xl border border-border/60 p-8 sm:p-12">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-24 -top-32 size-80 rounded-full bg-[radial-gradient(circle,oklch(0.31_0.02_250/0.07),transparent_70%)]"
          />
          <div className="relative max-w-2xl">
            <h1 className="font-display text-4xl font-semibold tracking-[-0.03em] sm:text-5xl">
              Pricing that follows your enrolment
            </h1>
            <p className="mt-4 leading-relaxed text-muted-foreground sm:text-lg">
              You pay for the number of active students in your school. Every plan includes
              unlimited staff accounts, the parent portal, the offline teacher app and AI credits.
              Your school can grow within its tier during a billing period — we warn you before you
              reach the limit instead of blocking you.
            </p>
          </div>
        </div>

        <ul className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {SUBSCRIPTION_TIERS.map((tier) => (
            <li
              key={tier.id}
              className="fn-panel flex flex-col p-7 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-raised"
            >
              <h2 className="font-display text-lg font-semibold">{tier.label}</h2>
              <p className="mt-4 font-display text-3xl font-semibold tracking-[-0.02em]">
                {naira(tier.monthlyPrice)}
              </p>
              <p className="text-sm text-muted-foreground">per month</p>
              <dl className="mt-5 space-y-2 border-t border-border/70 pt-5 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">AI credits</dt>
                  <dd className="font-medium tabular-nums">{numberFmt(tier.aiCredits)} / month</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Storage</dt>
                  <dd className="font-medium tabular-nums">{tier.storageGb} GB</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">SMS allowance</dt>
                  <dd className="font-medium tabular-nums">{numberFmt(tier.smsAllowance)}</dd>
                </div>
              </dl>
              <ul className="mt-5 flex-1 space-y-2.5 text-sm">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex gap-2.5">
                    <span className="grid size-5 shrink-0 place-items-center rounded-full bg-success-soft text-success">
                      <Check className="size-3" aria-hidden="true" />
                    </span>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
              <Button asChild className="mt-7">
                <Link to="/get-started" search={{ tier: tier.id }}>
                  Choose this plan
                </Link>
              </Button>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
