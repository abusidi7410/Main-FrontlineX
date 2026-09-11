import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Printer, X } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
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
import { useSession } from "@/auth/session";
import { dateTimeFmt, naira, titleCase } from "@/lib/format";
import { printHtml } from "@/lib/print";
import {
  listInvoices,
  listPayments,
  recordPayment,
  verifyPayment,
} from "@/services/finance.service";
import type { Invoice, Payment } from "@/types";

export const Route = createFileRoute("/_app/fees")({
  head: () => ({
    meta: [
      { title: "Fees — Frontline Nexus" },
      {
        name: "description",
        content: "Your children's school fee invoices, balances and payment receipts.",
      },
      { property: "og:title", content: "Fees — Frontline Nexus" },
      {
        property: "og:description",
        content: "Your children's school fee invoices, balances and payment receipts.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: FeesPage,
});

const SELF_SERVICE_METHODS: Payment["method"][] = ["card", "bank_transfer", "online", "ussd"];

function balanceOf(invoice: Invoice) {
  return Math.max(0, invoice.total - invoice.paid);
}

function printInvoice(invoice: Invoice, school: { name: string; address: string }) {
  const rows = invoice.items
    .map((item) => `<tr><td>${item.label}</td><td class="right">${naira(item.amount)}</td></tr>`)
    .join("");
  const ok = printHtml({
    title: "Invoice",
    bodyHtml: `<p class="school">${school.name} · ${school.address}</p>
<div class="doc">
<h1>Fee invoice</h1>
<p><strong>${invoice.studentName}</strong><br/>
${invoice.className} · ${invoice.term} · ${invoice.id}</p>
<table>
<thead><tr><th>Item</th><th class="right">Amount</th></tr></thead>
<tbody>${rows}
<tr><td class="total">Total due</td><td class="right total">${naira(invoice.total)}</td></tr>
<tr><td>Paid to date</td><td class="right">${naira(invoice.paid)}</td></tr>
<tr><td class="total">Outstanding balance</td><td class="right total">${naira(balanceOf(invoice))}</td></tr>
</tbody>
</table>
<p class="fine">Kindly settle the balance before the examination week. Payments can be made by card, bank transfer, online or USSD from the Fees page.</p>
</div>`,
  });
  if (!ok) toast.error("Allow pop-ups to print. You can then download the document.");
}

function printReceipt(payment: Payment, school: { name: string; address: string }) {
  const ok = printHtml({
    title: "Receipt",
    bodyHtml: `<p class="school">${school.name} · ${school.address}</p>
<div class="doc">
<h1>Payment receipt</h1>
<p><strong>${payment.studentName}</strong><br/>
${payment.reference} · ${dateTimeFmt(payment.createdAt)}</p>
<table>
<tbody>
<tr><td>Amount paid</td><td class="right">${naira(payment.amount)}</td></tr>
<tr><td>Method</td><td class="right">${titleCase(payment.method)}</td></tr>
<tr><td>Status</td><td class="right">${titleCase(payment.status)}</td></tr>
<tr><td>Recorded by</td><td class="right">${payment.recordedBy}</td></tr>
</tbody>
</table>
<p class="fine">This receipt confirms payment has been received and verified.</p>
</div>`,
  });
  if (!ok) toast.error("Allow pop-ups to print. You can then download the document.");
}

function FeesPage() {
  const { session } = useSession();
  const queryClient = useQueryClient();

  const invoicesQuery = useQuery({ queryKey: ["invoices", "fees"], queryFn: () => listInvoices() });
  const paymentsQuery = useQuery({ queryKey: ["payments", "fees"], queryFn: listPayments });

  const [activeInvoice, setActiveInvoice] = useState<Invoice | null>(null);

  const mine = (invoicesQuery.data ?? []).slice(0, 3);
  const receipts = (paymentsQuery.data ?? []).slice(0, 6);
  const billed = mine.reduce((sum, i) => sum + i.total, 0);
  const paid = mine.reduce((sum, i) => sum + i.paid, 0);
  const school = {
    name: session?.school?.name ?? "Al-Noor Model Academy",
    address: session?.school ? `${session.school.address}, ${session.school.state}` : "Nigeria",
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Fees"
        description="What each child owes this term, and every payment the school has recorded for you."
      />

      {invoicesQuery.isError || paymentsQuery.isError ? (
        <ErrorState
          onRetry={() => {
            void invoicesQuery.refetch();
            void paymentsQuery.refetch();
          }}
        />
      ) : invoicesQuery.isPending || paymentsQuery.isPending ? (
        <ListSkeleton />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Total billed this term" value={naira(billed)} />
            <StatCard label="Total paid" value={naira(paid)} tone="success" />
            <StatCard
              label="Outstanding balance"
              value={naira(Math.max(0, billed - paid))}
              tone={billed - paid > 0 ? "danger" : "success"}
            />
          </div>

          <section className="space-y-3">
            <h2 className="font-medium">Invoices</h2>
            {mine.length === 0 ? (
              <EmptyState
                title="No invoices yet"
                description="Invoices appear here as soon as the school issues them for the term."
              />
            ) : (
              <ul className="grid gap-3">
                {mine.map((invoice) => (
                  <li key={invoice.id} className="fn-panel space-y-3 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium">{invoice.studentName}</p>
                        <p className="text-sm text-muted-foreground">
                          {invoice.className} · {invoice.term} · {invoice.id}
                        </p>
                      </div>
                      <StatusBadge status={invoice.status} />
                    </div>
                    <ul className="space-y-1 text-sm">
                      {invoice.items.map((item) => (
                        <li key={item.label} className="flex justify-between gap-4">
                          <span className="text-muted-foreground">{item.label}</span>
                          <span className="tabular-nums">{naira(item.amount)}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
                      <p className="text-sm">
                        Balance{" "}
                        <span className="font-semibold tabular-nums">
                          {naira(balanceOf(invoice))}
                        </span>{" "}
                        <span className="text-muted-foreground">of {naira(invoice.total)}</span>
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => printInvoice(invoice, school)}
                        >
                          <Printer className="size-4" aria-hidden="true" />
                          Print invoice
                        </Button>
                        <Button
                          size="sm"
                          disabled={invoice.paid >= invoice.total}
                          onClick={() => setActiveInvoice(invoice)}
                        >
                          Pay now
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="font-medium">Payment history</h2>
            {receipts.length === 0 ? (
              <EmptyState
                title="No payments recorded"
                description="Once a payment is confirmed it appears here with a receipt."
              />
            ) : (
              <ul className="fn-panel divide-y">
                {receipts.map((payment) => (
                  <li key={payment.id} className="flex flex-wrap items-center gap-3 p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium tabular-nums">{naira(payment.amount)}</p>
                      <p className="text-sm text-muted-foreground">
                        {titleCase(payment.method)} · {payment.reference} ·{" "}
                        {dateTimeFmt(payment.createdAt)}
                      </p>
                    </div>
                    <StatusBadge status={payment.status} />
                    {payment.status === "verified" ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => printReceipt(payment, school)}
                      >
                        <Printer className="size-4" aria-hidden="true" />
                        Receipt
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <PaymentDialog
        invoice={activeInvoice}
        onClose={() => {
          setActiveInvoice(null);
        }}
        onPaid={() => {
          void queryClient.invalidateQueries({ queryKey: ["invoices"] });
          void queryClient.invalidateQueries({ queryKey: ["payments"] });
        }}
        school={school}
      />
    </div>
  );
}

function PaymentDialog({
  invoice,
  onClose,
  onPaid,
  school,
}: {
  invoice: Invoice | null;
  onClose: () => void;
  onPaid: () => void;
  school: { name: string; address: string };
}) {
  const open = invoice !== null;
  const [method, setMethod] = useState<Payment["method"]>("card");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState<Payment | null>(null);

  const balance = invoice ? balanceOf(invoice) : 0;
  const amountNumber = Number(amount);
  const amountValid = Number.isFinite(amountNumber) && amountNumber > 0 && amountNumber <= balance;

  const pay = async () => {
    if (!invoice || !amountValid || busy) return;
    setBusy(true);
    setConfirmed(null);
    try {
      const recorded = await recordPayment({
        invoiceId: invoice.id,
        amount: amountNumber,
        method,
      });
      const verified = await verifyPayment(recorded.id);
      setConfirmed(verified);
      toast.success(`${naira(verified.amount)} paid for ${verified.studentName}.`);
      onPaid();
    } catch {
      toast.error("We couldn't process that payment. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    if (busy) return;
    onClose();
    setConfirmed(null);
    setAmount("");
    setMethod("card");
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : close())}>
      <DialogContent
        className="sm:max-w-md"
        onPointerDownOutside={(e) => (busy ? e.preventDefault() : undefined)}
      >
        {confirmed ? (
          <>
            <DialogHeader>
              <DialogTitle>Payment received</DialogTitle>
              <DialogDescription>
                {confirmed.studentName} — {confirmed.reference}. A receipt is now in your payment
                history.
              </DialogDescription>
            </DialogHeader>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Amount</dt>
                <dd className="font-semibold tabular-nums">{naira(confirmed.amount)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Method</dt>
                <dd>{titleCase(confirmed.method)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Status</dt>
                <dd>
                  <StatusBadge status={confirmed.status} />
                </dd>
              </div>
            </dl>
            <DialogFooter className="gap-2 sm:gap-2">
              <Button variant="outline" onClick={() => printReceipt(confirmed, school)}>
                <Printer className="size-4" aria-hidden="true" />
                Print receipt
              </Button>
              <Button onClick={close}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Pay {invoice?.studentName}</DialogTitle>
              <DialogDescription>
                {invoice?.className} · {invoice?.term} · outstanding{" "}
                <span className="font-medium tabular-nums">{naira(balance)}</span>
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="pay-method">Payment method</Label>
                <Select
                  value={method}
                  onValueChange={(value) => setMethod(value as Payment["method"])}
                >
                  <SelectTrigger id="pay-method" className="h-12">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SELF_SERVICE_METHODS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {titleCase(option)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pay-amount">Amount (₦)</Label>
                <Input
                  id="pay-amount"
                  className="h-12"
                  inputMode="numeric"
                  value={amount}
                  placeholder={`${naira(balance)}`}
                  onChange={(event) => setAmount(event.target.value.replace(/[^0-9]/g, ""))}
                  aria-describedby="pay-amount-hint"
                />
                <p id="pay-amount-hint" className="text-sm text-muted-foreground">
                  Pay the full balance or a partial amount up to {naira(balance)}.
                </p>
              </div>
            </div>
            <DialogFooter className="gap-2 sm:gap-2">
              <Button variant="outline" onClick={close}>
                <X className="size-4" aria-hidden="true" />
                Cancel
              </Button>
              <Button onClick={() => void pay()} disabled={!amountValid || busy}>
                {busy ? "Processing payment…" : "Pay now"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
