import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BadgeCheck,
  Banknote,
  ClipboardCheck,
  Shield,
  Sparkles,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { BrandLockup } from "@/components/layout/brand";
import { SUBSCRIPTION_TIERS } from "@/constants/plans";
import { naira } from "@/lib/format";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Frontline Nexus — School Management for Nigerian Schools" },
      {
        name: "description",
        content:
          "Run your entire school from one secure system: students, attendance, results, fees, timetables and AI assistance. Built for Nigerian primary and secondary schools.",
      },
      { property: "og:title", content: "Frontline Nexus — School Management for Nigerian Schools" },
      {
        property: "og:description",
        content:
          "Students, attendance, results, fees and AI assistance in one secure school operating system. Works offline on teacher phones.",
      },
    ],
  }),
  component: LandingPage,
});

const FEATURES = [
  {
    icon: ClipboardCheck,
    title: "Attendance in seconds",
    body: "Teachers mark a full class from their phone — even with no internet. Records sync automatically when the network returns.",
  },
  {
    icon: BadgeCheck,
    title: "Results and report cards",
    body: "Configurable CA and exam weighting, approval workflow, and printable report cards with your school's branding.",
  },
  {
    icon: Banknote,
    title: "Fees without confusion",
    body: "Automatic invoices per class and term, cash and transfer recording, online payments, receipts and reconciliation.",
  },
  {
    icon: Sparkles,
    title: "AI that respects roles",
    body: "Lesson plans for teachers, performance insight for principals, fee summaries for bursars — each limited to authorised data.",
  },
  {
    icon: WifiOff,
    title: "Built for real networks",
    body: "Light pages, offline teacher app and low data usage, tested against slow 3G and low-end Android phones.",
  },
  {
    icon: Shield,
    title: "Secure by design",
    body: "Each school's data is fully isolated, every sensitive action is audited, and permissions are enforced on the server.",
  },
];

function LandingPage() {
  const entryTier = SUBSCRIPTION_TIERS[0]!;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" aria-label="Frontline Nexus home">
            <BrandLockup />
          </Link>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link to="/pricing">Pricing</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/login" search={{}}>
                Sign in
              </Link>
            </Button>
            <Button asChild className="hidden sm:inline-flex">
              <Link to="/get-started">Create your school</Link>
            </Button>
          </div>
        </div>
      </header>

      <section className="border-b border-border">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-primary">
            <Shield className="size-4" aria-hidden="true" /> We Develop. We Secure. We Connect.
          </p>
          <h1 className="mt-6 max-w-3xl font-display text-4xl font-semibold leading-[1.08] tracking-[-0.03em] sm:text-5xl lg:text-6xl">
            The operating system for your school
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            Frontline Nexus brings students, staff, attendance, results, fees and school
            communication into one calm, secure place — with AI support and an offline teacher app
            built for Nigerian classrooms.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg" className="min-h-12 text-base">
              <Link to="/get-started">
                Create your school <ArrowRight className="ml-2 size-5" aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="min-h-12 text-base">
              <Link to="/login" search={{}}>
                I already have an account
              </Link>
            </Button>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            From {naira(entryTier.monthlyPrice)}/month for up to 100 students. Teachers, parents and
            students are invited by your school — no public sign-up.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl font-semibold tracking-[-0.02em]">
            Everything a school actually does
          </h2>
          <p className="mt-3 text-muted-foreground">
            Powerful underneath, simple on the surface. No training required for your administrator
            or teachers.
          </p>
        </div>
        <ul className="mt-10 grid gap-x-12 lg:grid-cols-2">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="flex gap-4 border-t border-border py-6">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary">
                <feature.icon className="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 className="font-display text-lg font-semibold">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="border-t border-border/60 bg-muted/40">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-16 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-[-0.02em]">
              Ready to set up your school?
            </h2>
            <p className="mt-2 text-muted-foreground">
              Registration takes a few minutes. Your school is activated as soon as payment is
              confirmed.
            </p>
          </div>
          <Button asChild size="lg" className="min-h-12 shrink-0 text-base">
            <Link to="/get-started">Create your school</Link>
          </Button>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} Frontline Nexus. All rights reserved.</p>
          <nav aria-label="Footer" className="flex gap-4">
            <Link to="/pricing" className="hover:text-foreground">
              Pricing
            </Link>
            <Link to="/login" search={{}} className="hover:text-foreground">
              Sign in
            </Link>
            <Link to="/get-started" className="hover:text-foreground">
              Create school
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
