import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSession } from "@/auth/session";
import { dateTimeFmt, naira, titleCase } from "@/lib/format";
import {
  listInvoices,
  listPayments,
  recordPayment,
  verifyPayment,
} from "@/services/finance.service";
import type { Payment } from "@/types";

export const Route = createFileRoute("/_app/finance/")({
  head: () => ({
    meta: [
      { title: "Payments — Frontline Nexus" },
      {
        name: "description",
        content:
          "Record fee payments, verify transfers and issue receipts with a full audit trail.",
      },
      { property: "og:title", content: "Payments — Frontline Nexus" },
      {
        property: "og:description",
        content: "Record fee payments, verify transfers and issue receipts.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PaymentsPage,
});

const METHODS: Payment["method"][] = ["cash", "bank_transfer", "card", "pos", "ussd", "online"];

function PaymentsPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const invoices = useQuery({ queryKey: ["invoices", ""], queryFn: () => listInvoices() });
  const payments = useQuery({ queryKey: ["payments"], queryFn: listPayments });

  const [invoiceId, setInvoiceId] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<Payment["method"]>("cash");
  const [reference, setReference] = useState("");

  const record = useMutation({
    mutationFn: () =>
      recordPayment({
        invoiceId,
        amount: Number(amount),
        method,
        ...(reference ? { reference } : {}),
      }),
    onSuccess: async (payment) => {
      toast.success(
        `${naira(payment.amount)} recorded for ${payment.studentName}. Receipt ${payment.reference}.`,
      );
      setAmount("");
      setReference("");
      await queryClient.invalidateQueries({ queryKey: ["payments"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
    onError: () =>
      toast.error("We couldn't record that payment. Please check the amount and try again."),
  });

  const verify = useMutation({
    mutationFn: verifyPayment,
    onSuccess: async () => {
      toast.success("Payment verified.");
      await queryClient.invalidateQueries({ queryKey: ["payments"] });
    },
    onError: () => toast.error("Verification failed. Please try again."),
  });

  const canSubmit = invoiceId !== "" && Number(amount) > 0 && !record.isPending;

  return (
    <PermissionGate anyOf={["finance.read", "finance.write"]}>
      <div className="space-y-6">
        <PageHeader
          title="Payments"
          description="Every payment is receipted and tied to an invoice, so your records always reconcile."
          actions={
            <Button asChild variant="outline" className="h-11">
              <Link to="/finance/invoices">View invoices</Link>
            </Button>
          }
        />

        {can("finance.write") ? (
          <form
            className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (canSubmit) record.mutate();
            }}
          >
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="invoice">Invoice</Label>
              <Select value={invoiceId} onValueChange={setInvoiceId}>
                <SelectTrigger id="invoice" className="h-12">
                  <SelectValue placeholder="Select a student invoice" />
                </SelectTrigger>
                <SelectContent>
                  {(invoices.data ?? []).slice(0, 40).map((invoice) => (
                    <SelectItem key={invoice.id} value={invoice.id}>
                      {invoice.studentName} · {invoice.className} · owes{" "}
                      {naira(invoice.total - invoice.paid)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="amount">Amount (₦)</Label>
              <Input
                id="amount"
                inputMode="numeric"
                className="h-12"
                value={amount}
                onChange={(event) => setAmount(event.target.value.replace(/[^0-9]/g, ""))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="method">Method</Label>
              <Select
                value={method}
                onValueChange={(value) => setMethod(value as Payment["method"])}
              >
                <SelectTrigger id="method" className="h-12">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {METHODS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {titleCase(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="reference">Reference (optional)</Label>
              <Input
                id="reference"
                className="h-12"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            </div>
            <Button
              type="submit"
              className="h-12 text-base sm:col-span-2 sm:w-auto"
              disabled={!canSubmit}
            >
              {record.isPending ? "Recording…" : "Record payment"}
            </Button>
          </form>
        ) : null}

        {payments.isError ? (
          <ErrorState onRetry={() => void payments.refetch()} />
        ) : payments.isPending ? (
          <ListSkeleton />
        ) : (
          <ul className="fn-panel divide-y">
            {payments.data.map((payment) => (
              <li key={payment.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{payment.studentName}</p>
                  <p className="text-sm text-muted-foreground">
                    {titleCase(payment.method)} · {payment.reference} ·{" "}
                    {dateTimeFmt(payment.createdAt)} · by {payment.recordedBy}
                  </p>
                </div>
                <p className="font-medium tabular-nums">{naira(payment.amount)}</p>
                <StatusBadge status={payment.status} />
                {payment.status === "pending" && can("finance.verify") ? (
                  <Button
                    variant="outline"
                    className="h-11"
                    disabled={verify.isPending}
                    onClick={() => verify.mutate(payment.id)}
                  >
                    Verify
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}
