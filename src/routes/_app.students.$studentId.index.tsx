import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  ArrowLeftRight,
  Pencil,
  Printer,
  UserCheck,
  UserMinus,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { IfAllowed } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TransferStudentDialog } from "@/features/students/transfer-student-dialog";
import { useSession } from "@/auth/session";
import { dateFmt, dateTimeFmt, naira, percent } from "@/lib/format";
import {
  escapeHtml,
  printHtml,
  schoolHeading,
  type PrintSchoolProfile,
} from "@/lib/print";
import { listStudentInvoices, listStudentPayments } from "@/services/finance.service";
import { getStudent, reinstateStudent, suspendStudent } from "@/services/students.service";
import type { Invoice, Payment } from "@/types";

export const Route = createFileRoute("/_app/students/$studentId/")({
  head: () => ({
    meta: [
      { title: "Student profile — Frontline Nexus" },
      {
        name: "description",
        content: "Full student profile: attendance, results, fees and enrolment history.",
      },
      { property: "og:title", content: "Student profile — Frontline Nexus" },
      {
        property: "og:description",
        content: "Full student profile: attendance, results, fees and enrolment history.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StudentProfilePage,
});

function StudentProfilePage() {
  const { studentId } = Route.useParams();
  const queryClient = useQueryClient();
  const { session, can } = useSession();
  const [printing, setPrinting] = useState(false);
  const query = useQuery({
    queryKey: ["student", studentId],
    queryFn: () => getStudent(studentId),
  });

  const invalidateStudent = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["student", studentId] }),
      queryClient.invalidateQueries({ queryKey: ["students"] }),
    ]);

  const suspend = useMutation({
    mutationFn: () => suspendStudent(studentId),
    onSuccess: async (student) => {
      toast.success(`${student.firstName} ${student.lastName} has been suspended.`);
      await invalidateStudent();
    },
    onError: () => toast.error("We couldn't suspend this student. Please try again."),
  });

  const reinstate = useMutation({
    mutationFn: () => reinstateStudent(studentId),
    onSuccess: async (student) => {
      toast.success(`${student.firstName} ${student.lastName} is active again.`);
      await invalidateStudent();
    },
    onError: () => toast.error("We couldn't reinstate this student. Please try again."),
  });

  const [transferOpen, setTransferOpen] = useState(false);

  if (query.isError) {
    return (
      <ErrorState
        message="We couldn't find that student record."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <CardsSkeleton count={3} />;

  const student = query.data;

  /**
   * The registration document is assembled from records the server already
   * holds — the student, their enrolment history, their invoices and their
   * payments — plus the school's own saved profile. Nothing is stored or
   * duplicated for printing.
   */
  const printRegistrationDocument = async () => {
    if (printing) return;
    const school = session?.school;
    if (!school) {
      toast.error("Your school profile is missing. Save it in Settings before printing.");
      return;
    }
    setPrinting(true);
    try {
      // Finance endpoints require finance.read, so a viewer without it still
      // gets the document, just without the financial section.
      const withFinance = can("finance.read");
      let invoices: Invoice[] = [];
      let payments: Payment[] = [];
      if (withFinance) {
        [invoices, payments] = await Promise.all([
          listStudentInvoices(studentId),
          listStudentPayments(studentId),
        ]);
      }

      const profile: PrintSchoolProfile = {
        name: school.name,
        address: [school.address, school.state].filter(Boolean).join(", "),
        phone: school.phone,
        email: school.email,
        logoUrl: school.logoUrl,
      };
      const fullName = `${student.firstName} ${student.lastName}`;
      const history = student.enrollmentHistory;
      const entry =
        history.find((row) => row.session === school.currentSession) ??
        history.find((row) => row.status !== "not_enrolled") ??
        history[0];
      const registrationInvoice = invoices.find((invoice) => invoice.source === "admission");
      const outstanding = registrationInvoice
        ? Math.max(0, registrationInvoice.total - registrationInvoice.paid)
        : 0;

      const row = (label: string, value: string) =>
        `<tr><th scope="row">${escapeHtml(label)}</th><td>${value}</td></tr>`;

      const studentRows = [
        row("Full name", escapeHtml(fullName)),
        row("Admission number", escapeHtml(student.admissionNumber)),
        row("Date of birth", escapeHtml(dateFmt(student.dateOfBirth))),
        row("Gender", escapeHtml(student.gender)),
        row("Registration status", escapeHtml(student.status.replaceAll("_", " "))),
      ].join("");

      const guardianRows = [
        row("Guardian name", escapeHtml(student.guardianName)),
        row("Guardian phone", escapeHtml(student.guardianPhone)),
      ].join("");

      const academicRows = [
        row("Academic session", escapeHtml(entry?.session ?? school.currentSession ?? "—")),
        row("Class", escapeHtml(student.className)),
        row("Section / arm", escapeHtml(student.arm || "—")),
        row(
          "Enrollment",
          escapeHtml(
            entry
              ? `${entry.status.replaceAll("_", " ")}${
                  entry.className ? ` · ${entry.className}${entry.arm ?? ""}` : ""
                }`
              : "Not enrolled in any session yet",
          ),
        ),
      ].join("");

      let financialRows = "";
      let invoiceBreakdownHtml = "";
      if (!withFinance) {
        financialRows = row(
          "Financial details",
          "Not available for your account.",
        );
      } else if (registrationInvoice) {
        financialRows = [
          row("Registration invoice", escapeHtml(registrationInvoice.id)),
          row("Invoice total", naira(registrationInvoice.total)),
          row("Amount paid", naira(registrationInvoice.paid)),
          row("Outstanding registration balance", naira(outstanding)),
          row("Status", escapeHtml(registrationInvoice.status.replaceAll("_", " "))),
        ].join("");
        if (registrationInvoice.items.length) {
          invoiceBreakdownHtml = `<h2>Invoice breakdown</h2>
<table><thead><tr><th>Item</th><th class="right">Amount</th></tr></thead><tbody>${registrationInvoice.items
            .map(
              (item) =>
                `<tr><td>${escapeHtml(item.label)}</td><td class="right">${naira(item.amount)}</td></tr>`,
            )
            .join("")}</tbody></table>`;
        }
      } else {
        financialRows = row("Registration invoice", "No registration invoice on record.");
      }

      const paymentsHtml =
        withFinance && payments.length
          ? `<h2>Payments</h2>
<table><thead><tr><th>Reference</th><th>Date</th><th>Method</th><th class="right">Amount</th><th class="right">Status</th></tr></thead><tbody>${payments
              .map(
                (payment) =>
                  `<tr><td>${escapeHtml(payment.reference)}</td><td>${escapeHtml(
                    dateTimeFmt(payment.createdAt),
                  )}</td><td>${escapeHtml(payment.method.replaceAll("_", " "))}</td><td class="right">${naira(
                    payment.amount,
                  )}</td><td class="right">${escapeHtml(
                    payment.status.replaceAll("_", " "),
                  )}</td></tr>`,
              )
              .join("")}</tbody></table>`
          : "";

      const ok = printHtml({
        title: `Registration document — ${fullName}`,
        styles:
          "h2 { font-size: 15px; margin: 22px 0 8px; color: #0f172a; } .doc h1 + .fine { margin-top: -8px; }",
        bodyHtml: `${schoolHeading(profile)}
<div class="doc">
<h1>Student registration document</h1>
<p class="fine">Printed ${escapeHtml(dateTimeFmt(new Date().toISOString()))}</p>
<h2>Student</h2>
<table><tbody>${studentRows}</tbody></table>
<h2>Parent / guardian</h2>
<table><tbody>${guardianRows}</tbody></table>
<h2>Academic</h2>
<table><tbody>${academicRows}</tbody></table>
<h2>Financial</h2>
<table><tbody>${financialRows}</tbody></table>
${invoiceBreakdownHtml}
${paymentsHtml}
</div>`,
      });
      if (!ok) toast.error("Allow pop-ups to print. You can then download the document.");
    } catch {
      toast.error("We couldn't build the registration document. Please try again.");
    } finally {
      setPrinting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link
        to="/students"
        className="inline-flex items-center gap-2 font-medium text-primary hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to students
      </Link>

      <PageHeader
        title={`${student.firstName} ${student.lastName}`}
        description={`${student.admissionNumber} · ${student.className}${student.arm} · Guardian: ${student.guardianName} (${student.guardianPhone})`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={student.status} />
            <Button variant="outline" disabled={printing} onClick={() => void printRegistrationDocument()}>
              <Printer className="size-4" aria-hidden="true" />{" "}
              {printing ? "Preparing…" : "Registration document"}
            </Button>
            <IfAllowed permission="students.write">
              <Button asChild variant="outline">
                <Link to="/students/$studentId/edit" params={{ studentId }}>
                  <Pencil className="size-4" aria-hidden="true" /> Edit
                </Link>
              </Button>
              {student.status === "suspended" ? (
                <ConfirmDialog
                  trigger={
                    <Button variant="outline">
                      <UserCheck className="size-4" aria-hidden="true" /> Reinstate
                    </Button>
                  }
                  title="Reinstate this student?"
                  description={`${student.firstName} ${student.lastName} will become active again and can resume attendance, results and fee processing.`}
                  confirmLabel="Reinstate"
                  onConfirm={() => reinstate.mutate()}
                />
              ) : null}
              {student.status === "active" ? (
                <>
                  <ConfirmDialog
                    trigger={
                      <Button variant="outline">
                        <UserMinus className="size-4" aria-hidden="true" /> Suspend
                      </Button>
                    }
                    title="Suspend this student?"
                    description="A suspended student stays on record but can't be marked present, given results or charged fees. You can reinstate them anytime."
                    confirmLabel="Suspend student"
                    destructive
                    onConfirm={() => suspend.mutate()}
                  />
                  <Button variant="outline" onClick={() => setTransferOpen(true)}>
                    <ArrowLeftRight className="size-4" aria-hidden="true" /> Transfer
                  </Button>
                </>
              ) : null}
            </IfAllowed>
          </div>
        }
      />

      {student.status === "suspended" ? (
        <Alert variant="destructive">
          <AlertCircle className="size-4" aria-hidden="true" />
          <AlertTitle>This student is suspended</AlertTitle>
          <AlertDescription>
            They can no longer be marked present, given results or charged fees until reinstated.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Attendance"
          value={percent(student.attendanceRate)}
          tone={student.attendanceRate >= 75 ? "success" : "warning"}
        />
        <StatCard label="Term average" value={percent(student.average)} />
        <StatCard
          label="Outstanding fees"
          value={naira(student.outstandingFees)}
          tone={student.outstandingFees > 0 ? "warning" : "success"}
        />
      </div>

      <section className="fn-panel p-5" aria-labelledby="bio-heading">
        <h2 id="bio-heading" className="font-semibold">
          Personal details
        </h2>
        <dl className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">Date of birth</dt>
            <dd className="font-medium">{dateFmt(student.dateOfBirth)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Gender</dt>
            <dd className="font-medium capitalize">{student.gender}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Class</dt>
            <dd className="font-medium">
              {student.className}
              {student.arm}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Guardian</dt>
            <dd className="font-medium">
              {student.guardianName} · {student.guardianPhone}
            </dd>
          </div>
          {student.transferredTo ? (
            <div>
              <dt className="text-sm text-muted-foreground">Transferred to</dt>
              <dd className="font-medium">
                {student.transferredTo.schoolName} · {dateFmt(student.transferredTo.transferredAt)}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      <section className="fn-panel overflow-hidden" aria-labelledby="history-heading">
        <div className="border-b px-5 py-4">
          <h2 id="history-heading" className="font-semibold">
            Enrolment history
          </h2>
        </div>
        <ul className="divide-y">
          {student.enrollmentHistory.map((entry) => (
            <li key={entry.sessionId} className="flex flex-wrap items-center gap-x-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{entry.session}</p>
                {entry.reviewNote ? (
                  <p className="mt-1 text-sm text-warning">{entry.reviewNote}</p>
                ) : null}
              </div>
              <p className="text-muted-foreground">
                {entry.className}
                {entry.arm ? ` · ${entry.arm}` : ""}
              </p>
              <p className="text-muted-foreground">
                {entry.status.replaceAll("_", " ")}
                {entry.flaggedForReview ? " · flagged for review" : ""}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <TransferStudentDialog
        studentId={student.id}
        studentName={`${student.firstName} ${student.lastName}`}
        open={transferOpen}
        onOpenChange={setTransferOpen}
      />
    </div>
  );
}
