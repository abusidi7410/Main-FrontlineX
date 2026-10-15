import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string | undefined;
  actions?: ReactNode | undefined;
  eyebrow?: string | undefined;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <span aria-hidden="true" className="fn-rule" />
          {eyebrow ? <span className="fn-eyebrow">{eyebrow}</span> : null}
        </div>
        <h1 className="mt-2.5 font-display text-[1.7rem] font-semibold leading-[1.15] tracking-[-0.02em] text-balance sm:text-[2rem]">
          {title}
        </h1>
        {description ? (
          <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
