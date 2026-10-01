import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiRequestError } from "@/api/client";
import { useSession } from "@/auth/session";
import { useDebounced } from "@/hooks/use-debounced";
import { naira } from "@/lib/format";
import { getAcademicStructure, TERM_OPTIONS } from "@/services/academics.service";
import { generateInvoices, listInvoicePage } from "@/services/finance.service";
import { CLASSES } from "@/constants/reference";

export const Route = createFileRoute("/_app/finance/invoices")({
  head: () => ({
    meta: [
      { title: "Invoices — Frontline Nexus" },
      {
        name: "description",
        content: "Termly fee invoices with balances, part payments and status per student.",
      },
      { property: "og:title", content: "Invoices — Frontline Nexus" },
      {
        property: "og:description",
        content: "Termly fee invoices with balances and status per student.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: InvoicesPage,
});

function InvoicesPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["invoices", debounced, page],
    queryFn: () => listInvoicePage(debounced, page),
  });
  const [generateOpen, setGenerateOpen] = useState(false);

  return (
    <PermissionGate permission="finance.read">
      <div className="space-y-6">
        <PageHeader
          title="Invoices"
          description={
            query.data
              ? `Showing ${query.data.results.length} of ${query.data.count} invoices.`
              : "Invoices and balances for your school."
          }
          actions={
            can("finance.write") ? (
              <Button className="h-11" onClick={() => setGenerateOpen(true)}>
                <Plus className="size-4" aria-hidden="true" />
                Generate invoices
              </Button>
            ) : undefined
          }
        />

        <Input
          className="h-11"
          placeholder="Search by student name or invoice number"
          aria-label="Search invoices"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : query.data.results.length === 0 ? (
          <EmptyState
            title="No invoices found"
            description="Generate invoices from a class fee structure, or try a different search."
            action={
              can("finance.structure") ? (
                <Button asChild variant="outline" className="h-11">
                  <Link to="/settings">Set up the Payment Structure</Link>
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="fn-panel overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left">
              <caption className="sr-only">Fee invoices</caption>
              <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Student
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Class
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Total
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Paid
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Balance
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {query.data.results.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="px-4 py-3">
                      <span className="font-medium">{invoice.studentName}</span>
                      <span className="block text-sm text-muted-foreground">
                        {invoice.source === "admission" ? "One-time registration" : invoice.term}
                      </span>
                    </td>
                    <td className="px-4 py-3">{invoice.className}</td>
                    <td className="px-4 py-3 tabular-nums">{naira(invoice.total)}</td>
                    <td className="px-4 py-3 tabular-nums">{naira(invoice.paid)}</td>
                    <td className="px-4 py-3 font-medium tabular-nums">
                      {naira(invoice.total - invoice.paid)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={invoice.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {query.data && query.data.totalPages > 1 ? (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Page {query.data.page} of {query.data.totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="h-10"
                disabled={page <= 1 || query.isFetching}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                className="h-10"
                disabled={page >= query.data.totalPages || query.isFetching}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}

        <GenerateInvoicesDialog
          open={generateOpen}
          onOpenChange={(open) => {
            setGenerateOpen(open);
            if (!open) {
              void queryClient.invalidateQueries({ queryKey: ["invoices"] });
              void queryClient.invalidateQueries({ queryKey: ["finance-summary"] });
            }
          }}
        />
      </div>
    </PermissionGate>
  );
}

/**
 * Billing only. Prices live in Settings > Payment Structure, which is a
 * separate screen on purpose: saving a structure there can create real debt for
 * students who registered before fees existed, and that must not be a
 * side effect of a button labelled "Generate invoices".
 */
function GenerateInvoicesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const academics = useQuery({ queryKey: ["academics"], queryFn: () => getAcademicStructure() });
  const classes = academics.data?.classes ?? CLASSES;

  const [className, setClassName] = useState(classes[0] ?? "");
  const [term, setTerm] = useState(academics.data?.term ?? "First Term");
  const [overwrite, setOverwrite] = useState(false);

  useEffect(() => {
    if (!open || !academics.data) return;
    setClassName(classes[0] ?? "");
    setTerm(academics.data.term || "First Term");
  }, [open, academics.data, classes]);

  const generate = useMutation({
    mutationFn: () =>
      generateInvoices({ className, term, ...(overwrite ? { overwrite: true } : {}) }),
    onSuccess: (result) => {
      toast.success(
        `Created ${result.generated} invoice${result.generated === 1 ? "" : "s"}` +
          (result.updated > 0 ? ` and recalculated ${result.updated}` : "") +
          ` for ${result.term} (${result.totalStudents} student${result.totalStudents === 1 ? "" : "s"}).`,
      );
      void queryClient.invalidateQueries({ queryKey: ["invoices"] });
      void queryClient.invalidateQueries({ queryKey: ["finance-summary"] });
      onOpenChange(false);
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError ? error.message : "Could not generate invoices.",
      );
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate term invoices</DialogTitle>
          <DialogDescription>
            One invoice is created per active student in the class, priced from the Payment
            Structure in Settings. Already-drafted invoices for the term are left untouched.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="gen-class">Class</Label>
            <Select value={className} onValueChange={setClassName}>
              <SelectTrigger id="gen-class" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {classes.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gen-term">Term</Label>
            <Select value={term} onValueChange={setTerm}>
              <SelectTrigger id="gen-term" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TERM_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <label className="flex items-center gap-2 rounded-lg border border-muted bg-muted/30 px-3 py-2 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-foreground"
            checked={overwrite}
            onChange={(event) => setOverwrite(event.target.checked)}
          />
          Recalculate existing invoices for this term
        </label>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            disabled={!className || !term || generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? "Generating…" : "Generate invoices"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
