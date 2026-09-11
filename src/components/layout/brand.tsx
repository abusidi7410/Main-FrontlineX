import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-9 shrink-0 place-items-center rounded-2xl bg-primary font-display text-sm font-bold text-primary-foreground shadow-[0_6px_14px_-6px_oklch(0.31_0.02_250/0.6),inset_0_1px_0_oklch(1_0_0/0.12)]",
        className,
      )}
    >
      FN
    </span>
  );
}

export function BrandLockup({ subtitle }: { subtitle?: string }) {
  return (
    <span className="flex items-center gap-2.5">
      <BrandMark />
      <span className="flex flex-col leading-tight">
        <span className="font-display text-sm font-semibold tracking-tight">Frontline Nexus</span>
        <span className="text-[11px] text-muted-foreground">
          {subtitle ?? "We Develop. We Secure. We Connect."}
        </span>
      </span>
    </span>
  );
}
