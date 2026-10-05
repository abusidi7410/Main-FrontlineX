import { dateTimeFmt, naira, titleCase } from "@/lib/format";
import { escapeHtml, printHtml, schoolHeading, type PrintSchoolProfile } from "@/lib/print";
import type { Invoice, Payment } from "@/types";

export type { PrintSchoolProfile };

export function invoiceBalance(invoice: Invoice): number {
  return Math.max(0, invoice.total - invoice.paid);
}

/**
 * Turns a school record — from the session or from the profile endpoint — into
 * the letterhead fields a printed document needs. The school is always the
 * caller's own, so nothing here can print another school's details.
 */
export function toPrintProfile(
  school:
    | {
        name: string;
        address?: string | null | undefined;
        state?: string | null | undefined;
        phone?: string | null | undefined;
        email?: string | null | undefined;
        logoUrl?: string | null | undefined;
      }
    | null
    | undefined,
): PrintSchoolProfile | null {
  if (!school?.name) return null;
  return {
    name: school.name,
    address: [school.address, school.state].filter(Boolean).join(", ") || undefined,
    phone: school.phone ?? undefined,
    email: school.email ?? undefined,
    logoUrl: school.logoUrl ?? null,
  };
}

export function invoiceKind(invoice: Invoice): string {
  return invoice.source === "admission" ? "Registration invoice" : "Fee invoice";
}

/**
 * The printable body of a fee or registration invoice. Built from the invoice
 * record the server already returned, so a printed invoice can never disagree
 * with what the parent or bursar sees on screen.
 */
export function buildInvoiceHtml(invoice: Invoice, school: PrintSchoolProfile): string {
  const kind = invoiceKind(invoice);
  const rows = invoice.items
    .map(
      (item) =>
        `<tr><td>${escapeHtml(item.label)}</td><td class="right">${naira(item.amount)}</td></tr>`,
    )
    .join("");
  return `${schoolHeading(school)}
<div class="doc">
<h1>${kind}</h1>
<p><strong>${escapeHtml(invoice.studentName)}</strong><br/>
${escapeHtml(invoice.className)} · ${invoice.source === "admission" ? "One-time registration" : escapeHtml(invoice.term)} · ${escapeHtml(invoice.id)}</p>
<table>
<thead><tr><th>Item</th><th class="right">Amount</th></tr></thead>
<tbody>${rows}
<tr><td class="total">Total due</td><td class="right total">${naira(invoice.total)}</td></tr>
<tr><td>Paid to date</td><td class="right">${naira(invoice.paid)}</td></tr>
<tr><td class="total">Outstanding balance</td><td class="right total">${naira(invoiceBalance(invoice))}</td></tr>
</tbody>
</table>
<p class="fine">Kindly settle the balance before the examination week. Payments can be made by card, bank transfer, online or USSD from the Fees page.</p>
</div>`;
}

/**
 * The printable body of a payment receipt. Every value comes from the payment
 * record itself — reference, amount, method, status and recorder — so a receipt
 * can never be issued for the wrong payment.
 */
export function buildReceiptHtml(payment: Payment, school: PrintSchoolProfile): string {
  const { invoiceTotal, invoicePaid } = payment;
  const hasInvoiceTotals = invoiceTotal !== undefined && invoicePaid !== undefined;
  const invoiceRows = hasInvoiceTotals
    ? `<tr><td>Invoice</td><td class="right">${escapeHtml(payment.invoiceId)}</td></tr>
<tr><td>Invoice total</td><td class="right">${naira(invoiceTotal)}</td></tr>
<tr><td>Invoice paid to date</td><td class="right">${naira(invoicePaid)}</td></tr>
<tr><td class="total">Remaining balance</td><td class="right total">${naira(Math.max(0, invoiceTotal - invoicePaid))}</td></tr>`
    : "";
  return `${schoolHeading(school)}
<div class="doc">
<h1>Payment receipt</h1>
<p><strong>${escapeHtml(payment.studentName)}</strong><br/>
${payment.admissionNumber ? `Admission number ${escapeHtml(payment.admissionNumber)}<br/>` : ""}
${escapeHtml(payment.reference)} · ${dateTimeFmt(payment.createdAt)}</p>
<table>
<tbody>
<tr><td>Amount paid</td><td class="right">${naira(payment.amount)}</td></tr>
<tr><td>Method</td><td class="right">${titleCase(payment.method)}</td></tr>
<tr><td>Status</td><td class="right">${titleCase(payment.status)}</td></tr>
${invoiceRows}
<tr><td>Recorded by</td><td class="right">${escapeHtml(payment.recordedBy)}</td></tr>
</tbody>
</table>
<p class="fine">This receipt confirms payment has been received and verified.</p>
</div>`;
}

export function printInvoiceDocument(invoice: Invoice, school: PrintSchoolProfile | null): boolean {
  if (!school) {
    return false;
  }
  return printHtml({ title: invoiceKind(invoice), bodyHtml: buildInvoiceHtml(invoice, school) });
}

export function printReceiptDocument(payment: Payment, school: PrintSchoolProfile | null): boolean {
  if (!school) return false;
  return printHtml({ title: "Receipt", bodyHtml: buildReceiptHtml(payment, school) });
}
