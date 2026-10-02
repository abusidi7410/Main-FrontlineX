import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-9 shrink-0 place-items-center rounded-lg bg-brass font-display text-sm font-bold tracking-tight text-brass-foreground shadow-[var(--shadow-brass)] ring-1 ring-inset ring-brass-foreground/15",
        className,
      )}
    >
      FN
    </span>
  );
}

/**
 * `tone="inverse"` is for the navy sidebar / nav sheet, where the lockup must
 * resolve against sidebar tokens. The default `surface` tone is for the light
 * marketing surfaces.
 */
export function BrandLockup({
  subtitle,
  tone = "surface",
}: {
  subtitle?: string;
  tone?: "surface" | "inverse";
}) {
  return (
    <span className="flex items-center gap-2.5">
      <BrandMark />
      <span className="flex flex-col leading-tight">
        <span
          className={cn(
            "font-display text-[0.9375rem] font-semibold tracking-[-0.012em]",
            tone === "inverse" ? "text-sidebar-foreground" : "text-foreground",
          )}
        >
          Frontline Nexus
        </span>
        <span
          className={cn(
            "text-[11px]",
            tone === "inverse" ? "text-sidebar-foreground/60" : "text-muted-foreground",
          )}
        >
          {subtitle ?? "We Develop. We Secure. We Connect."}
        </span>
      </span>
    </span>
  );
}
