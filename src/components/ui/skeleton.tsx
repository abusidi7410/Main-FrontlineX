import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("fn-skeleton", className)} {...props} />;
}

export { Skeleton };
