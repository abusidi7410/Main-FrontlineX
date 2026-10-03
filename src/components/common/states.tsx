import { AlertTriangle, Inbox, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode | undefined;
  icon?: ReactNode | undefined;
}) {
  return (
    <div className="fn-panel flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="fn-icon-tile size-12 text-primary">
        {icon ?? <Inbox className="size-6" aria-hidden="true" />}
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="max-w-md text-muted-foreground">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  onRetry,
  message = "Something went wrong while loading this information. Please try again.",
}: {
  onRetry?: (() => void) | undefined;
  message?: string;
}) {
  return (
    <div role="alert" className="fn-panel flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="fn-icon-tile size-12 text-warning">
        <AlertTriangle className="size-6" aria-hidden="true" />
      </div>
      <h2 className="text-lg font-semibold">We couldn't load this</h2>
      <p className="max-w-md text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function OfflineNotice() {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-[18px] border border-warning/25 bg-warning-soft px-4 py-3 text-sm shadow-[inset_1px_1px_2px_oklch(0.31_0.02_250/0.04)]"
    >
      <WifiOff className="mt-0.5 size-5 text-warning" aria-hidden="true" />
      <p>
        You're offline. Your changes are saved on this device and will be synchronised automatically
        when internet access returns.
      </p>
    </div>
  );
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="fn-panel divide-y" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-4">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="hidden h-4 w-24 sm:block" />
        </div>
      ))}
    </div>
  );
}

export function CardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="fn-panel space-y-3 p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </div>
  );
}
