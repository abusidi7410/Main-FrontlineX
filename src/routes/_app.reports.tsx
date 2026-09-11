import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Printer } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { naira, numberFmt, percent } from "@/lib/format";
import { printHtml } from "@/lib/print";
import { useSession } from "@/auth/session";
import { listInvoices } from "@/services/finance.service";
import { getResultSheets, getStaff } from "@/services/school.service";
import { listStudents } from "@/services/students.service";
import { getReportCard, type ReportCard } from "@/services/reports.service";
import type { Invoice, ResultSheet, StaffMember, Student } from "@/types";

export const Route = createFileRoute("/_app/reports")({
  head: () => ({
    meta: [
      { title: "Reports — Frontline Nexus" },
      {
        name: "description",
        content: "Enrolment, attendance, academic and revenue reports for your school.",
      },
      { property: "og:title", content: "Reports — Frontline Nexus" },
      {
        property: "og:description",
        content: "Enrolment, attendance, academic and revenue reports for your school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ReportsPage,
});

const REPORT_PACKS = [
  {
    id: "enrolment",
    title: "Enrolment summary",
    description: "Students per class and arm, with gender split and admission trend.",
  },
  {
    id: "attendance",
    title: "Attendance register",
    description: "Daily and termly attendance percentages per class and teacher.",
  },
  {
    id: "academic",
    title: "Academic performance",
    description: "Subject averages, pass rates and top performers per class.",
  },
  {
    id: "finance",
    title: "Fee collection",
    description: "Invoiced vs collected fees, outstanding balances and payment methods.",
  },
  {
    id: "staff",
    title: "Staff directory",
    description: "Teaching load, subjects and class assignments for every staff member.",
  },
] as const;

type PackId = (typeof REPORT_PACKS)[number]["id"];

function escapeCsv(cell: string | number) {
  return `"${String(cell).replace(/"/g, '""')}"`;
}

function rowsFor(
  id: PackId,
  roster: Student[],
  invoices: Invoice[],
  staff: StaffMember[],
  sheets: ResultSheet[],
): { headers: string[]; rows: (string | number)[][] } {
  switch (id) {
    case "enrolment":
      return {
        headers: ["Admission number", "Student", "Class", "Gender", "Status"],
        rows: roster.map((s) => [
          s.admissionNumber,
          `${s.firstName} ${s.lastName}`,
          `${s.className}${s.arm}`,
          s.gender,
          s.status,
        ]),
      };
    case "attendance":
      return {
        headers: ["Admission number", "Student", "Class", "Attendance %"],
        rows: roster.map((s) => [
          s.admissionNumber,
          `${s.firstName} ${s.lastName}`,
          `${s.className}${s.arm}`,
          s.attendanceRate,
        ]),
      };
    case "academic":
      return {
        headers: ["Student", "Class", "Subject", "CA 1", "CA 2", "Assignment", "Exam", "Total"],
        rows: sheets.flatMap((sheet) =>
          sheet.rows.map((row) => [
            row.studentName,
            sheet.className,
            sheet.subject,
            row.ca1 ?? "",
            row.ca2 ?? "",
            row.assignment ?? "",
            row.exam ?? "",
            (row.ca1 ?? 0) + (row.ca2 ?? 0) + (row.assignment ?? 0) + (row.exam ?? 0),
          ]),
        ),
      };
    case "finance":
      return {
        headers: ["Student", "Class", "Invoice", "Billed (₦)", "Paid (₦)", "Balance (₦)"],
        rows: invoices.map((invoice) => [
          invoice.studentName,
          invoice.className,
          invoice.id,
          invoice.total,
          invoice.paid,
          Math.max(0, invoice.total - invoice.paid),
        ]),
      };
    case "staff":
      return {
        headers: ["Name", "Role", "Email", "Phone", "Subjects", "Classes", "Status"],
        rows: staff.map((member) => [
          member.fullName,
          member.role,
          member.email,
          member.phone,
          member.subjects.join("; "),
          member.classes.join("; "),
          member.status,
        ]),
      };
  }
}

function downloadCsv(fileName: string, headers: string[], rows: (string | number)[][]) {
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => escapeCsv(cell)).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
  toast.success(`Downloaded ${fileName}`);
}

function printPack(
  packTitle: string,
  headers: string[],
  rows: (string | number)[][],
  schoolLabel: string,
) {
  const head = headers.map((h) => `<th>${h}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${String(cell)}</td>`).join("")}</tr>`)
    .join("");
  const ok = printHtml({
    title: packTitle,
    bodyHtml: `<p class="school">${schoolLabel}</p>
<div class="doc">
<h1>${packTitle}</h1>
<table>
<thead><tr>${head}</tr></thead>
<tbody>${body}</tbody>
</table>
</div>`,
  });
  if (!ok) toast.error("Allow pop-ups to print. You can then save the report as PDF.");
}

function reportCardStyles() {
  return `
  .rc-head { text-align: center; border-bottom: 3px double #0f172a; padding-bottom: 12px; margin-bottom: 16px; }
  .rc-head .name { font-family: Georgia, serif; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }
  .rc-meta { width: 100%; }
  .rc-meta td { border: none; padding: 2px 4px; }
  .rc-remark { border: 1px solid #cbd5e1; padding: 10px 12px; margin-top: 12px; border-radius: 6px; }
  .grade-chip { display: inline-block; min-width: 24px; text-align: center; border: 1px solid #94a3b8; border-radius: 4px; padding: 0 4px; font-weight: 700; }
  `;
}

function printReportCard(card: ReportCard) {
  const sheetRows = card.subjects
    .map(
      (s) => `<tr>
<td>${s.subject}</td>
<td class="center">${s.ca1 ?? "—"}</td>
<td class="center">${s.ca2 ?? "—"}</td>
<td class="center">${s.assignment ?? "—"}</td>
<td class="center">${s.exam ?? "—"}</td>
<td class="center">${s.total}</td>
<td class="center"><span class="grade-chip">${s.grade}</span></td>
</tr>`,
    )
    .join("");
  const ok = printHtml({
    title: "Report card",
    styles: reportCardStyles(),
    bodyHtml: `<p class="school">${card.school.name} · ${card.school.address}</p>
<div class="doc">
<div class="rc-head">
<div class="name">Report card</div>
<div class="muted">${card.term} · ${card.session}</div>
</div>
<table class="rc-meta">
<tr><td class="muted">Student</td><td><strong>${card.student.name}</strong></td>
<td class="muted">Admission</td><td>${card.student.admissionNumber}</td></tr>
<tr><td class="muted">Class</td><td>${card.student.className}${card.student.arm}</td>
<td class="muted">Attendance</td><td>${percent(card.student.attendanceRate)}</td></tr>
</table>
<table>
<thead><tr><th>Subject</th><th class="center">CA 1</th><th class="center">CA 2</th><th class="center">Assignment</th><th class="center">Exam</th><th class="center">Total</th><th class="center">Grade</th></tr></thead>
<tbody>${sheetRows}
<tr><td class="total">Overall</td><td colspan="4" class="right muted">Average score</td><td class="center total">${card.average}%</td><td></td></tr>
</tbody>
</table>
<div class="rc-remark"><strong>Class teacher's remark:</strong> ${card.remark}</div>
<p class="fine">This report card is generated from the school's approved results. Signed copies are available at the school office.</p>
</div>`,
  });
  if (!ok) toast.error("Allow pop-ups to print. You can then save the report card as PDF.");
}

function ReportsPage() {
  const { session } = useSession();
  const students = useQuery({
    queryKey: ["students", "reports"],
    queryFn: () => listStudents({ pageSize: 1000 }),
  });
  const invoices = useQuery({ queryKey: ["invoices", "reports"], queryFn: () => listInvoices() });
  const staff = useQuery({ queryKey: ["staff"], queryFn: getStaff });
  const sheets = useQuery({ queryKey: ["results", "reports"], queryFn: getResultSheets });

  const [className, setClassName] = useState("");
  const [studentId, setStudentId] = useState("");

  const isPending = students.isPending || invoices.isPending || staff.isPending || sheets.isPending;
  const isError = students.isError || invoices.isError || staff.isError || sheets.isError;

  const roster = students.data?.results ?? [];
  const billed = (invoices.data ?? []).reduce((sum, i) => sum + i.total, 0);
  const collected = (invoices.data ?? []).reduce((sum, i) => sum + i.paid, 0);
  const avgAttendance = roster.length
    ? roster.reduce((sum, s) => sum + s.attendanceRate, 0) / roster.length
    : 0;

  const classes = [...new Set(roster.map((student) => student.className))].sort((a, b) =>
    a.localeCompare(b),
  );
  const studentsInClass = className
    ? roster.filter((student) => student.className === className)
    : [];

  const reportCardQuery = useQuery({
    queryKey: ["report-card", studentId],
    queryFn: () => getReportCard(studentId!),
    enabled: studentId !== "",
  });

  const card = reportCardQuery.data;

  return (
    <PermissionGate permission="reports.read">
      <div className="space-y-6">
        <PageHeader
          title="Reports"
          description="Termly reporting packs you can review on screen or download for your board and proprietors."
        />

        {isError ? (
          <ErrorState
            onRetry={() => {
              void students.refetch();
              void invoices.refetch();
              void staff.refetch();
              void sheets.refetch();
            }}
          />
        ) : isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label="Students on roll"
                value={numberFmt(students.data?.count ?? 0)}
                hint="Active and pending records"
              />
              <StatCard
                label="Staff"
                value={numberFmt(staff.data?.length ?? 0)}
                hint="Teaching and administrative"
              />
              <StatCard
                label="Average attendance"
                value={percent(avgAttendance)}
                tone={avgAttendance >= 85 ? "success" : "warning"}
                hint="This term to date"
              />
              <StatCard
                label="Fees collected"
                value={naira(collected)}
                tone="success"
                hint={`${percent(billed ? (collected / billed) * 100 : 0)} of ${naira(billed)} billed`}
              />
            </div>

            <section className="space-y-3">
              <h2 className="font-medium">Report cards</h2>
              <div className="fn-panel grid gap-4 p-5 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor="rc-class" className="text-sm font-medium">
                    Class
                  </label>
                  <Select
                    value={className}
                    onValueChange={(value) => {
                      setClassName(value);
                      setStudentId("");
                    }}
                  >
                    <SelectTrigger id="rc-class" className="h-11">
                      <SelectValue placeholder="Select a class" />
                    </SelectTrigger>
                    <SelectContent>
                      {classes.map((name) => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="rc-student" className="text-sm font-medium">
                    Student
                  </label>
                  <Select value={studentId} onValueChange={setStudentId} disabled={!className}>
                    <SelectTrigger id="rc-student" className="h-11">
                      <SelectValue
                        placeholder={className ? "Select a student" : "Pick a class first"}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {studentsInClass.map((student) => (
                        <SelectItem key={student.id} value={student.id}>
                          {student.firstName} {student.lastName} · {student.admissionNumber}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            {studentId === "" ? null : reportCardQuery.isPending ? (
              <ListSkeleton />
            ) : reportCardQuery.isError || !card ? (
              <EmptyState
                title="No report card yet"
                description="Students get a report card once at least one subject has approved or published results."
              />
            ) : (
              <section className="fn-panel overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
                  <div>
                    <h3 className="font-semibold">
                      {card.student.name} — {card.student.className}
                      {card.student.arm}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {card.student.admissionNumber} · {card.term} · {card.session}
                    </p>
                  </div>
                  <Button onClick={() => printReportCard(card)}>
                    <Printer className="size-4" aria-hidden="true" />
                    Print report card
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[36rem] text-left">
                    <caption className="sr-only">Report card for {card.student.name}</caption>
                    <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                      <tr>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Subject
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          CA 1
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          CA 2
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Assignment
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Exam
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Total
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Grade
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {card.subjects.map((subject) => (
                        <tr key={subject.subject}>
                          <td className="px-4 py-3">{subject.subject}</td>
                          <td className="px-4 py-3 tabular-nums">{subject.ca1 ?? "—"}</td>
                          <td className="px-4 py-3 tabular-nums">{subject.ca2 ?? "—"}</td>
                          <td className="px-4 py-3 tabular-nums">{subject.assignment ?? "—"}</td>
                          <td className="px-4 py-3 tabular-nums">{subject.exam ?? "—"}</td>
                          <td className="px-4 py-3 font-medium tabular-nums">{subject.total}</td>
                          <td className="px-4 py-3">
                            <span className="inline-flex size-6 items-center justify-center rounded border border-foreground/30 text-sm font-bold">
                              {subject.grade}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t bg-muted/30">
                        <td className="px-4 py-3 font-semibold" colSpan={5}>
                          Average score
                        </td>
                        <td className="px-4 py-3 font-semibold tabular-nums">{card.average}%</td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <div className="space-y-2 border-t px-5 py-4 text-sm">
                  <p>
                    <span className="font-medium">Attendance:</span>{" "}
                    {percent(card.student.attendanceRate)}
                  </p>
                  <p>
                    <span className="font-medium">Class teacher's remark:</span> {card.remark}
                  </p>
                </div>
              </section>
            )}

            <ul className="grid gap-4 md:grid-cols-2">
              {REPORT_PACKS.map((pack) => {
                const { headers, rows } = rowsFor(
                  pack.id,
                  roster,
                  invoices.data ?? [],
                  staff.data ?? [],
                  sheets.data ?? [],
                );
                const schoolLabel = [session?.school?.name, session?.school?.address]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <li key={pack.id} className="fn-panel flex flex-col gap-3 p-5">
                    <div className="flex items-start gap-3">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                        <FileText className="size-5" aria-hidden="true" />
                      </span>
                      <div className="min-w-0">
                        <h2 className="font-medium">{pack.title}</h2>
                        <p className="text-sm text-muted-foreground">{pack.description}</p>
                      </div>
                    </div>
                    <div className="mt-auto flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={rows.length === 0}
                        onClick={() => downloadCsv(`${pack.id}-${Date.now()}.csv`, headers, rows)}
                      >
                        <Download className="size-4" aria-hidden="true" />
                        CSV
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={rows.length === 0}
                        onClick={() => printPack(pack.title, headers, rows, schoolLabel)}
                      >
                        <Printer className="size-4" aria-hidden="true" />
                        Print
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
