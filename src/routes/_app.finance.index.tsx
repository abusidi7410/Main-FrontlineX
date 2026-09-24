import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
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
import { ApiRequestError } from "@/api/client";
import { useSession } from "@/auth/session";
import { dateTimeFmt, naira, titleCase } from "@/lib/format";
import {
  cancelPayment,
  listInvoices,
  listPayments,
  recordPayment,
  reversePayment,
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

  const selectedInvoice = (invoices.data ?? []).find((invoice) => invoice.id === invoiceId);
  const balance = selectedInvoice ? Math.max(0, selectedInvoice.total - selectedInvoice.paid) : 0;
  const amountNumber = Number(amount);
  const withinBalance = Number.isFinite(amountNumber) && amountNumber <= balance;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["payments"] });
    await queryClient.invalidateQueries({ queryKey: ["invoices"] });
  };

  const record = useMutation({
    mutationFn: () =>
      recordPayment({
        invoiceId,
        amount: amountNumber,
        method,
        ...(reference ? { reference } : {}),
      }),
    onSuccess: async (payment) => {
      toast.success(
        `${naira(payment.amount)} recorded for ${payment.studentName}. Receipt ${payment.reference}.`,
      );
      setAmount("");
      setReference("");
      await refresh();
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "We couldn't record that payment. Please check the amount and try again.",
      );
    },
  });

  const verify = useMutation({
    mutationFn: verifyPayment,
    onSuccess: async () => {
      toast.success("Payment verified.");
      await refresh();
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "Verification failed. Please try again.",
      );
    },
  });

  const reverse = useMutation({
    mutationFn: reversePayment,
    onSuccess: async () => {
      toast.success("Payment reversed — the invoice balance has been restored.");
      await refresh();
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError ? error.message : "Could not reverse this payment.",
      );
    },
  });

  const cancel = useMutation({
    mutationFn: cancelPayment,
    onSuccess: async () => {
      toast.success("Pending payment cancelled.");
      await refresh();
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError ? error.message : "Could not cancel this payment.",
      );
    },
  });

  const canSubmit =
    invoiceId !== "" && Number(amount) > 0 && withinBalance && !record.isPending;

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
              <p id="amount-hint" className="text-sm text-muted-foreground">
                {selectedInvoice
                  ? `Outstanding balance: ${naira(balance)} of ${naira(selectedInvoice.total)}`
                  : "Select an invoice to see its outstanding balance."}
              </p>
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
                {payment.status === "pending" && can("finance.write") ? (
                  <ConfirmDialog
                    title="Cancel this payment?"
                    description={`${naira(payment.amount)} for ${payment.studentName} (${payment.reference}) will be cancelled and never credited to the invoice.`}
                    confirmLabel="Cancel payment"
                    destructive
                    trigger={
                      <Button
                        variant="ghost"
                        className="h-11 text-destructive"
                        disabled={cancel.isPending}
                      >
                        Cancel
                      </Button>
                    }
                    onConfirm={() => cancel.mutate(payment.id)}
                  />
                ) : null}
                {payment.status === "verified" && can("finance.write") ? (
                  <ConfirmDialog
                    title="Reverse this payment?"
                    description={`${naira(payment.amount)} will be removed from ${payment.studentName}'s invoice balance and the payment marked reversed.`}
                    confirmLabel="Reverse payment"
                    destructive
                    trigger={
                      <Button
                        variant="ghost"
                        className="h-11 text-destructive"
                        disabled={reverse.isPending}
                      >
                        Reverse
                      </Button>
                    }
                    onConfirm={() => reverse.mutate(payment.id)}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}