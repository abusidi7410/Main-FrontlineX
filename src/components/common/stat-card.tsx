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
    <div className="group relative overflow-hidden rounded-xl border border-border bg-card p-5 text-card-foreground shadow-[var(--shadow-card)] transition-[border-color,box-shadow] duration-150 hover:border-foreground/15 hover:shadow-[var(--shadow-raised)]">
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5 bg-brass/70" />
      <div className="flex items-start justify-between gap-3">
        <p className="fn-eyebrow pt-1">{label}</p>
        <div className="flex items-center gap-2">
          {trend}
          {icon ? (
            <span
              aria-hidden="true"
              className="grid size-9 shrink-0 place-items-center rounded-lg border border-brass/25 bg-brass-soft text-brass transition-colors duration-150 group-hover:border-brass/45"
            >
              {icon}
            </span>
          ) : null}
        </div>
      </div>
      <p
        className={cn(
          "mt-3 text-[28px] font-semibold leading-none tracking-[-0.02em] tabular-nums",
          toneClass,
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-2.5 text-[13px] leading-relaxed text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
