import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string | undefined;
  tone?: "default" | "success" | "warning" | "danger" | undefined;
  icon?: ReactNode | undefined;
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  }[tone];

  return (
    <div className="fn-panel fn-panel-hover flex flex-col p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-medium text-muted-foreground">{label}</p>
        {icon ? (
          <span aria-hidden="true" className="fn-icon-tile size-9 shrink-0 text-primary">
            {icon}
          </span>
        ) : null}
      </div>
      <p
        className={cn(
          "mt-3 font-display text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] tabular-nums sm:text-[2rem]",
          toneClass,
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-[13px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
