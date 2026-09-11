import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Phone } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { getUssdConfig } from "@/services/school.service";

export const Route = createFileRoute("/_app/ussd")({
  head: () => ({
    meta: [
      { title: "USSD — Frontline Nexus" },
      {
        name: "description",
        content: "Let parents check balances, pay fees and get results from any phone with USSD.",
      },
      { property: "og:title", content: "USSD — Frontline Nexus" },
      {
        property: "og:description",
        content: "USSD access for parents on any basic phone.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: UssdPage,
});

function UssdPage() {
  const query = useQuery({ queryKey: ["ussd"], queryFn: getUssdConfig });

  return (
    <PermissionGate permission="settings.read">
      <div className="space-y-6">
        <PageHeader
          title="USSD"
          description="Parents can check fees, pay and see results from any phone — no app or data bundle needed."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : query.data.enabled ? (
          <>
            <section className="fn-panel flex flex-wrap items-center gap-6 p-6">
              <span className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                <Phone className="size-8" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-muted-foreground">Active on every Nigerian network</p>
                <p className="mt-1 flex flex-wrap items-center gap-3">
                  <span className="font-display text-3xl font-bold tracking-tight">
                    {query.data.fullCode}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {query.data.shortCode} · {query.data.commands.length} services
                  </span>
                </p>
              </div>
              <Button
                variant="outline"
                onClick={() => {
                  void navigator.clipboard?.writeText(query.data.fullCode).then(
                    () => toast.success(`${query.data.fullCode} copied to clipboard.`),
                    () => toast.error("Clipboard access was blocked."),
                  );
                }}
              >
                <Copy className="size-4" aria-hidden="true" />
                Copy code
              </Button>
            </section>

            <section className="space-y-3">
              <h2 className="font-medium">What parents can do</h2>
              <ol className="fn-panel divide-y">
                {query.data.commands.map((command) => (
                  <li key={command.code} className="flex flex-wrap items-center gap-3 p-4">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted font-semibold">
                      {command.code}
                    </span>
                    <p className="min-w-0 flex-1 text-sm">{command.description}</p>
                  </li>
                ))}
              </ol>
            </section>

            <section className="fn-panel space-y-2 p-5 text-sm text-muted-foreground">
              <h2 className="font-medium text-foreground">How it works</h2>
              <p>Dial {query.data.fullCode} from any phone and follow the menu.</p>
              <p>
                Payments go through your configured gateway and the school verifies every
                transaction before it appears on an invoice.
              </p>
              <p>Standard network call rates apply — no data bundle is required.</p>
            </section>
          </>
        ) : (
          <section className="fn-panel space-y-2 p-6">
            <h2 className="font-medium">USSD is not enabled</h2>
            <p className="text-sm text-muted-foreground">
              This feature is included with your plan but needs to be activated and given your
              school's short code by the Frontline Nexus support team.
            </p>
          </section>
        )}
      </div>
    </PermissionGate>
  );
}
