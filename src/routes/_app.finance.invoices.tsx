import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
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
import { compactNaira, naira, numberFmt } from "@/lib/format";
import { getAcademicStructure, TERM_OPTIONS } from "@/services/academics.service";
import {
  generateInvoices,
  getFeeStructure,
  listInvoices,
  type FeeItem,
} from "@/services/finance.service";
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
  const query = useQuery({
    queryKey: ["invoices", debounced],
    queryFn: () => listInvoices(debounced),
  });
  const [generateOpen, setGenerateOpen] = useState(false);

  const outstanding = query.data?.reduce((sum, i) => sum + (i.total - i.paid), 0) ?? 0;

  return (
    <PermissionGate permission="finance.read">
      <div className="space-y-6">
        <PageHeader
          title="Invoices"
          description={`Outstanding across the current term: ${compactNaira(outstanding)}.`}
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
          onChange={(event) => setSearch(event.target.value)}
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : query.data.length === 0 ? (
          <EmptyState
            title="No invoices found"
            description="Generate invoices from a class fee structure, or try a different search."
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
                {query.data.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="px-4 py-3">
                      <span className="font-medium">{invoice.studentName}</span>
                      <span className="block text-sm text-muted-foreground">{invoice.term}</span>
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

        <GenerateInvoicesDialog
          open={generateOpen}
          onOpenChange={(open) => {
            setGenerateOpen(open);
            if (!open) void queryClient.invalidateQueries({ queryKey: ["invoices"] });
          }}
        />
      </div>
    </PermissionGate>
  );
}

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
  const [rows, setRows] = useState<FeeItem[]>([]);
  const [overwrite, setOverwrite] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (academics.data) {
      setClassName(classes[0] ?? "");
      setTerm(academics.data.term || "First Term");
    }
    void getFeeStructure()
      .then((structure) => setRows(structure.items))
      .catch(() => setRows([]));
  }, [open, academics.data, classes]);

  const total = rows.reduce((sum, row) => sum + row.amount, 0);

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
      onOpenChange(false);
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError ? error.message : "Could not generate invoices.",
      );
    },
  });

  const updateRow = (index: number, patch: Partial<FeeItem>) => {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate term invoices</DialogTitle>
          <DialogDescription>
            One invoice is created per active student in the class, using the fee items below.
            Already-drafted invoices for the term are left untouched.
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

        <div className="space-y-2">
          <Label>Fee items</Label>
          {rows.length === 0 ? (
            <p className="rounded-lg border p-3 text-sm text-muted-foreground">
              No fee structure yet. Add items — each is the amount every student in the class
              will be billed.
            </p>
          ) : null}
          {rows.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                className="h-11 flex-1"
                value={row.label}
                placeholder="Item label"
                onChange={(event) => updateRow(index, { label: event.target.value })}
              />
              <Input
                className="h-11 w-32"
                inputMode="numeric"
                value={row.amount}
                placeholder={naira(0)}
                onChange={(event) =>
                  updateRow(index, { amount: Number(event.target.value.replace(/[^0-9]/g, "")) })
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-11 text-muted-foreground hover:text-destructive"
                onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
              >
                <Trash2 className="size-4" aria-hidden="true" />
                <span className="sr-only">Remove {row.label}</span>
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-10"
            onClick={() => setRows((prev) => [...prev, { label: "", amount: 0, className: "*" }])}
          >
            <Plus className="size-4" aria-hidden="true" />
            Add item
          </Button>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-muted bg-muted/30 px-3 py-2 text-sm">
          <label className="flex items-center gap-2 font-medium">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              checked={overwrite}
              onChange={(event) => setOverwrite(event.target.checked)}
            />
            Recalculate existing invoices for this term
          </label>
          <span className="font-semibold tabular-nums">Total per student: {numberFmt(total)}</span>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            disabled={!className || !term || rows.length === 0 || rows.some((r) => !r.label || r.amount <= 0)}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? "Generating…" : "Generate invoices"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}