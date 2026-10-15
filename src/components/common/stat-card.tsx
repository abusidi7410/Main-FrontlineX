import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
  trend,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode | undefined;
  tone?: "default" | "success" | "warning" | "danger" | undefined;
  icon?: ReactNode | undefined;
  trend?: ReactNode | undefined;
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  }[tone];

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-border/80 bg-card p-5 text-card-foreground shadow-[var(--shadow-card)] transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-foreground/10 hover:shadow-[var(--shadow-raised)]">
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-brass via-brass/60 to-transparent" />
      <div className="flex items-start justify-between gap-3">
        <p className="fn-eyebrow pt-1.5">{label}</p>
        <div className="flex items-center gap-2">
          {trend}
          {icon ? (
            <span
              aria-hidden="true"
              className="grid size-10 shrink-0 place-items-center rounded-xl border border-border/70 bg-gradient-to-b from-muted to-muted/60 text-foreground shadow-sm transition-colors duration-200 group-hover:border-brass/40 group-hover:text-brass"
            >
              {icon}
            </span>
          ) : null}
        </div>
      </div>
      <p
        className={cn(
          "mt-3 text-[30px] font-semibold leading-none tracking-[-0.025em] tabular-nums",
          toneClass,
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
