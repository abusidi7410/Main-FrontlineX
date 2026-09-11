import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { titleCase } from "@/lib/format";

const TONES: Record<string, string> = {
  active: "bg-success-soft text-success border-success/25",
  verified: "bg-success-soft text-success border-success/25",
  paid: "bg-success-soft text-success border-success/25",
  synced: "bg-success-soft text-success border-success/25",
  published: "bg-success-soft text-success border-success/25",
  approved: "bg-success-soft text-success border-success/25",
  present: "bg-success-soft text-success border-success/25",
  pending: "bg-warning-soft text-warning border-warning/25",
  pending_payment: "bg-warning-soft text-warning border-warning/25",
  part_paid: "bg-warning-soft text-warning border-warning/25",
  grace: "bg-warning-soft text-warning border-warning/25",
  invited: "bg-warning-soft text-warning border-warning/25",
  late: "bg-warning-soft text-warning border-warning/25",
  under_review: "bg-info-soft text-info border-info/25",
  submitted: "bg-info-soft text-info border-info/25",
  trial: "bg-info-soft text-info border-info/25",
  excused: "bg-info-soft text-info border-info/25",
  failed: "bg-destructive/10 text-destructive border-destructive/25",
  suspended: "bg-destructive/10 text-destructive border-destructive/25",
  unpaid: "bg-destructive/10 text-destructive border-destructive/25",
  absent: "bg-destructive/10 text-destructive border-destructive/25",
  reversed: "bg-destructive/10 text-destructive border-destructive/25",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-medium",
        TONES[status] ?? "bg-muted text-muted-foreground border-border",
        className,
      )}
    >
      {titleCase(status)}
    </Badge>
  );
}
