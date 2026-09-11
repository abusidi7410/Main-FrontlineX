import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { BrandLockup } from "@/components/layout/brand";

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen flex-col bg-background">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[420px] bg-[radial-gradient(ellipse_at_top,oklch(0.31_0.02_250/0.05),transparent_65%)]"
      />
      <header className="relative z-10">
        <div className="mx-auto flex h-16 max-w-6xl items-center px-4 sm:px-6">
          <Link to="/" aria-label="Frontline Nexus home">
            <BrandLockup />
          </Link>
        </div>
      </header>
      <main className="relative z-10 mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12 sm:px-6">
        <section className="fn-panel fn-enter w-full px-7 py-9 sm:px-9">
          <h1 className="font-display text-3xl font-semibold tracking-[-0.025em]">{title}</h1>
          {description ? (
            <p className="mt-2.5 leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
          <div className="mt-8">{children}</div>
          {footer ? (
            <div className="mt-8 flex flex-col gap-2 border-t border-border/70 pt-6 text-sm text-muted-foreground">
              {footer}
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
