import { describe, expect, it } from "vitest";
import {
  buildInvoiceHtml,
  buildReceiptHtml,
  invoiceBalance,
  invoiceKind,
  toPrintProfile,
} from "@/lib/documents";
import type { Invoice, Payment } from "@/types";

const school = {
  name: "Riverside Primary School",
  address: "12 Ada Street, Port Harcourt, Rivers State",
  phone: "+234 800 000 0000",
  email: "fees@riverside.test",
  logoUrl: "https://cdn.example.test/logo.png",
};

const invoice: Invoice = {
  id: "INV-2026-0007",
  studentId: "stu_1",
  studentName: "Amina Bello",
  className: "Primary 3",
  term: "Second Term",
  source: "bulk",
  total: 150000,
  paid: 50000,
  items: [
    { label: "Tuition", amount: 120000 },
    { label: "Development levy", amount: 30000 },
  ],
  status: "part_paid",
};

const payment: Payment = {
  id: "pay_1",
  invoiceId: "INV-2026-0007",
  studentName: "Amina Bello",
  admissionNumber: "RPS/2026/0042",
  amount: 50000,
  method: "bank_transfer",
  status: "verified",
  reference: "RPS-PAY-9F2A",
  recordedBy: "Bursar Ade",
  createdAt: "2026-09-18T10:30:00.000Z",
  invoiceTotal: 150000,
  invoicePaid: 50000,
};

describe("buildReceiptHtml", () => {
  it("uses the correct payment", () => {
    const html = buildReceiptHtml(payment, school);
    expect(html).toContain("Amina Bello");
    expect(html).toContain("RPS/2026/0042");
    expect(html).toContain("RPS-PAY-9F2A");
    expect(html).toContain("₦50,000");
    expect(html).toContain("Bank Transfer");
    expect(html).toContain("Verified");
    expect(html).toContain("Bursar Ade");
  });

  it("uses the correct school profile, never a hardcoded school", () => {
    const html = buildReceiptHtml(payment, school);
    expect(html).toContain("Riverside Primary School");
    expect(html).toContain("12 Ada Street, Port Harcourt, Rivers State");
    expect(html).toContain("+234 800 000 0000");
    expect(html).toContain("fees@riverside.test");
    expect(html).toContain("https://cdn.example.test/logo.png");
    expect(html).not.toContain("Al-Noor");
  });

  it("shows the invoice position and remaining balance", () => {
    const html = buildReceiptHtml(payment, school);
    expect(html).toContain("INV-2026-0007");
    expect(html).toContain("₦150,000");
    expect(html).toContain("₦100,000");
  });

  it("omits invoice totals the payment record does not carry", () => {
    const withoutTotals: Payment = { ...payment };
    delete withoutTotals.invoiceTotal;
    delete withoutTotals.invoicePaid;
    const html = buildReceiptHtml(withoutTotals, school);
    expect(html).not.toContain("Invoice total");
  });

  it("never issues a receipt for the wrong payment", () => {
    const html = buildReceiptHtml({ ...payment, reference: "RPS-PAY-0001" }, school);
    expect(html).toContain("RPS-PAY-0001");
    expect(html).not.toContain("RPS-PAY-9F2A");
  });
});

describe("buildInvoiceHtml", () => {
  it("shows every line item and the outstanding balance", () => {
    const html = buildInvoiceHtml(invoice, school);
    expect(html).toContain("Tuition");
    expect(html).toContain("₦120,000");
    expect(html).toContain("Development levy");
    expect(html).toContain("Riverside Primary School");
    expect(html).toContain("INV-2026-0007");
    expect(html).toContain("₦100,000");
  });

  it("labels a registration invoice separately from a term fee invoice", () => {
    expect(invoiceKind(invoice)).toBe("Fee invoice");
    expect(invoiceKind({ ...invoice, source: "admission" })).toBe("Registration invoice");
    expect(buildInvoiceHtml({ ...invoice, source: "admission" }, school)).toContain(
      "Registration invoice",
    );
  });

  it("never reports a negative balance", () => {
    expect(invoiceBalance({ ...invoice, paid: 200000 })).toBe(0);
  });
});

describe("toPrintProfile", () => {
  it("joins the school's own address and state", () => {
    expect(
      toPrintProfile({ name: "Riverside", address: "12 Ada Street", state: "Rivers State" }),
    ).toEqual({
      name: "Riverside",
      address: "12 Ada Street, Rivers State",
      phone: undefined,
      email: undefined,
      logoUrl: null,
    });
  });

  it("returns null when there is no school to print for", () => {
    expect(toPrintProfile(null)).toBeNull();
    expect(toPrintProfile({ name: "" })).toBeNull();
  });
});
