import { createFileRoute, Link } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BrandLockup } from "@/components/layout/brand";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — Frontline Nexus School Management" },
      {
        name: "description",
        content:
          "Prepaid wallet pricing for Frontline Nexus. Fund your wallet, activate students per month, pay only for who you use.",
      },
      { property: "og:title", content: "Frontline Nexus pricing" },
      {
        property: "og:description",
        content:
          "One prepaid wallet, per-student monthly access. No fixed subscriptions, no plan limits.",
      },
    ],
  }),
  component: PricingPage,
});

const STEPS = [
  {
    title: "1. Create your school",
    body: "Register in a few minutes. Your school starts with an empty wallet — nothing to pay up front.",
  },
  {
    title: "2. Fund your wallet",
    body: "Top up any amount by card or bank transfer through our secure payment provider. Every kobo stays yours until a real charge occurs.",
  },
  {
    title: "3. Activate students",
    body: "Each student you activate gets a full month of access across attendance, results and records — charged once from the wallet.",
  },
  {
    title: "4. Only pay for who you use",
    body: "No fixed subscriptions, no per-plan student caps. A student you never activate costs nothing; renewals happen month by month while funded.",
  },
];

const INCLUDED = [
  "Unlimited staff accounts",
  "Parent portal",
  "Offline teacher app",
  "AI assistant",
  "Transaction history and audit trail",
];

function PricingPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-surface">
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
        <div className="max-w-2xl border-l-2 border-primary py-1 pl-5">
          <h1 className="font-display text-4xl font-semibold tracking-[-0.03em] sm:text-5xl">
            One wallet, pay per student
          </h1>
          <p className="mt-4 leading-relaxed text-muted-foreground sm:text-lg">
            No subscriptions, no plan limits. Your school wallet holds your money, and each
            activated student costs one small monthly fee — only for the students you actually use.
            The exact per-student price is set on the platform and shown inside your Wallet before
            you pay anything.
          </p>
        </div>

        <ul className="mt-12 grid gap-4 md:grid-cols-2">
          {STEPS.map((step) => (
            <li key={step.title} className="fn-panel p-7">
              <h2 className="font-display text-lg font-semibold">{step.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ul>

        <div className="fn-panel mt-4 p-7">
          <h2 className="font-display text-lg font-semibold">Everything is included</h2>
          <ul className="mt-4 grid gap-2.5 sm:grid-cols-2">
            {INCLUDED.map((feature) => (
              <li key={feature} className="flex gap-2.5 text-sm">
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-success-soft text-success">
                  <Check className="size-3" aria-hidden="true" />
                </span>
                <span>{feature}</span>
              </li>
            ))}
          </ul>
          <Button asChild className="mt-7">
            <Link to="/get-started">Create your school</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
