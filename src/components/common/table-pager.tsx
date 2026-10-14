import { Button } from "@/components/ui/button";

interface TablePagerProps {
  page: number;
  pageSize: number;
  count: number;
  onPageChange: (page: number) => void;
  itemLabel?: string;
  /** While true both buttons are disabled (e.g. a page fetch in flight). */
  disabled?: boolean;
}

/** Shared server-pagination footer: "Page x of y" + Previous/Next.
 *
 * Every paged table uses this so pagination looks and behaves the same
 * everywhere. Render it only when there is at least one row.
 */
export function TablePager({
  page,
  pageSize,
  count,
  onPageChange,
  itemLabel,
  disabled = false,
}: TablePagerProps) {
  if (count <= 0) return null;
  const totalPages = Math.max(1, Math.ceil(count / Math.max(pageSize, 1)));
  const firstShown = (page - 1) * pageSize + 1;
  const lastShown = Math.min(page * pageSize, count);
  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-muted-foreground">
        {itemLabel
          ? `Showing ${firstShown}–${lastShown} of ${count} ${itemLabel}`
          : `Page ${page} of ${totalPages}`}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
