import { Link } from "@tanstack/react-router";
import { AlertTriangle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AttentionItem {
  id: string;
  label: string;
  to: string;
  tone?: "warning" | "danger" | "info";
}

export function AttentionList({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return (
      <div className="fn-panel p-5">
        <h2 className="font-semibold">Attention required</h2>
        <p className="mt-1 text-muted-foreground">
          Nothing needs your attention right now. Everything is up to date.
        </p>
      </div>
    );
  }

  return (
    <section className="fn-panel overflow-hidden" aria-labelledby="attention-heading">
      <div className="border-b border-border/70 px-5 py-4">
        <h2 id="attention-heading" className="font-semibold">
          Attention required
        </h2>
      </div>
      <ul className="mx-3 my-3 space-y-1">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={item.to}
              className="group flex items-center gap-3 rounded-xl px-2.5 py-3 transition-all duration-150 hover:bg-muted/60"
            >
              <span
                className={cn(
                  "fn-icon-tile size-9 shrink-0",
                  item.tone === "danger"
                    ? "text-destructive"
                    : item.tone === "info"
                      ? "text-info"
                      : "text-warning",
                )}
              >
                <AlertTriangle className="size-4.5" aria-hidden="true" />
              </span>
              <span className="flex-1 text-[15px]">{item.label}</span>
              <ChevronRight
                className="size-5 shrink-0 text-muted-foreground/60 transition-colors group-hover:text-muted-foreground"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
