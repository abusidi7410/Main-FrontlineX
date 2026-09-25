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
    <div className="group rounded-2xl border border-border/70 bg-card/90 p-5 text-card-foreground shadow-sm backdrop-blur-md transition-[box-shadow,transform,background-color] duration-300 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        <div className="flex items-center gap-2">
          {trend}
          {icon ? (
            <span
              aria-hidden="true"
              className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted/70 text-primary"
            >
              {icon}
            </span>
          ) : null}
        </div>
      </div>
      <p
        className={cn(
          "mt-4 text-[30px] font-bold leading-none tracking-[-0.03em] tabular-nums",
          toneClass,
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-2 text-[13px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
