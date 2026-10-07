import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { naira, percent } from "@/lib/format";
import { getMyPublishedResults } from "@/services/school.service";
import { getChildAttendance, getChildPromotion, listChildren } from "@/services/children.service";
import { getReportCard } from "@/services/reports.service";
import type { MyPublishedResult, Student } from "@/types";

export const Route = createFileRoute("/_app/children")({
  head: () => ({
    meta: [
      { title: "My children — Frontline Nexus" },
      {
        name: "description",
        content: "Attendance, results and fee balance for each of your children.",
      },
      { property: "og:title", content: "My children — Frontline Nexus" },
      {
        property: "og:description",
        content: "Attendance, results and fee balance for each of your children.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ChildrenPage,
});

const SUGGESTION_LABEL: Record<string, string> = {
  promote: "Promote",
  conditional: "Conditional",
  repeat: "Repeat",
  review: "Review",
};

function SuggestionNote({ suggested }: { suggested: string | null }) {
  const tone =
    suggested === "promote"
      ? "text-success"
      : suggested === "conditional"
        ? "text-warning"
        : suggested === "repeat"
          ? "text-destructive"
          : "text-muted-foreground";
  return <span className={`font-medium ${tone}`}>{SUGGESTION_LABEL[suggested ?? ""] ?? "—"}</span>;
}

function ReportCardTab({ childId }: { childId: string }) {
  const query = useQuery({
    queryKey: ["report-card", childId],
    queryFn: () => getReportCard(childId),
  });
  const card = query.data;

  if (query.isError) {
    return <p className="text-sm text-muted-foreground">We couldn't load this report card.</p>;
  }
  if (query.isPending) return <ListSkeleton rows={3} />;
  if (!card) {
    return (
      <EmptyState
        title="No report card yet"
        description="Students get a report card once at least one subject has approved or published results."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <p className="text-sm text-muted-foreground">Term average</p>
          <p className="font-medium tabular-nums">{percent(card.average)}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Attendance</p>
          <p className="font-medium tabular-nums">{percent(card.student.attendanceRate)}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Class position</p>
          <p className="font-medium tabular-nums">
            {card.position ? `#${card.position.rank} of ${card.position.outOf}` : "—"}
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <caption className="sr-only">Report card for {card.student.name}</caption>
          <thead className="border-b bg-muted/40 text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Subject
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                CA 1
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                CA 2
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Assignment
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Exam
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Total
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Grade
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {card.subjects.map((subject) => (
              <tr key={subject.subject}>
                <td className="px-3 py-2">{subject.subject}</td>
                <td className="px-3 py-2 tabular-nums">{subject.ca1 ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums">{subject.ca2 ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums">{subject.assignment ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums">{subject.exam ?? "—"}</td>
                <td className="px-3 py-2 font-medium tabular-nums">{subject.total}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex size-6 items-center justify-center rounded border border-foreground/30 text-sm font-bold">
                    {subject.grade}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t bg-muted/30">
              <td className="px-3 py-2 font-semibold" colSpan={5}>
                Average score
              </td>
              <td className="px-3 py-2 font-semibold tabular-nums">{card.average}%</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      <p className="text-sm">
        <span className="font-medium">Class teacher's remark:</span> {card.remark}
      </p>
      {card.promotion ? (
        <p className="text-sm">
          <span className="font-medium">Promotion suggestion:</span>{" "}
          <SuggestionNote suggested={card.promotion.suggested} />
          {card.promotion.nextClass ? ` · Next class ${card.promotion.nextClass}` : ""}
        </p>
      ) : null}
    </div>
  );
}

function AttendanceTab({ childId }: { childId: string }) {
  const query = useQuery({
    queryKey: ["child-attendance", childId],
    queryFn: () => getChildAttendance(childId),
  });

  if (query.isError) {
    return <p className="text-sm text-muted-foreground">We couldn't load this register.</p>;
  }
  if (query.isPending) return <ListSkeleton rows={3} />;

  const data = query.data;
  const { summary, records } = data;
  const rate = summary.attendanceRate;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <div>
          <p className="text-muted-foreground">Attendance</p>
          <p className="font-medium tabular-nums">{rate == null ? "—" : percent(rate)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Present</p>
          <p className="font-medium tabular-nums">{summary.present}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Late</p>
          <p className="font-medium tabular-nums">{summary.late}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Absent</p>
          <p className="font-medium tabular-nums">{summary.absent}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Excused</p>
          <p className="font-medium tabular-nums">{summary.excused}</p>
        </div>
      </div>

      {records.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No attendance was recorded for {data.session}.
        </p>
      ) : (
        <ul className="divide-y text-sm">
          {records.map((row) => (
            <li key={row.date} className="flex items-center justify-between gap-3 py-2">
              <span className="text-muted-foreground">{row.date}</span>
              <span className="capitalize">{row.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PromotionTab({ childId }: { childId: string }) {
  const query = useQuery({
    queryKey: ["child-promotion", childId],
    queryFn: () => getChildPromotion(childId),
  });

  if (query.isError) {
    return <p className="text-sm text-muted-foreground">We couldn't load this suggestion.</p>;
  }
  if (query.isPending) return <ListSkeleton rows={3} />;

  const body = query.data;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">Suggestion</span>
        <SuggestionNote suggested={body.suggested} />
      </div>
      <p>{body.reason}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-muted-foreground">Average</p>
          <p className="font-medium tabular-nums">
            {body.average == null ? "—" : percent(body.average)}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Attendance</p>
          <p className="font-medium tabular-nums">
            {body.attendanceRate == null ? "—" : percent(body.attendanceRate)}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Subjects assessed</p>
          <p className="font-medium tabular-nums">{body.subjectsAssessed}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Failed</p>
          <p className="font-medium tabular-nums">{body.failedSubjects}</p>
        </div>
      </div>
      <p>
        <span className="text-muted-foreground">Next class: </span>
        <span className="font-medium">
          {body.isFinalClass ? "Graduated (no next class)" : (body.nextClass ?? "—")}
        </span>
      </p>
    </div>
  );
}

function ChildCard({ child, results }: { child: Student; results: MyPublishedResult[] }) {
  const [tab, setTab] = useState("overview");
  const myResults = results.filter((result) => result.studentId === child.id);

  return (
    <li className="fn-panel flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-semibold">
            {child.firstName} {child.lastName}
          </h2>
          <p className="text-sm text-muted-foreground">
            {child.className}
            {child.arm} · {child.admissionNumber}
          </p>
        </div>
        <StatusBadge status={child.status} />
      </div>

      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Attendance</dt>
          <dd className="font-medium tabular-nums">{percent(child.attendanceRate)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Term average</dt>
          <dd className="font-medium tabular-nums">{child.average.toFixed(1)}%</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Fees owed</dt>
          <dd
            className={
              child.outstandingFees > 0
                ? "font-medium tabular-nums text-destructive"
                : "font-medium tabular-nums text-success"
            }
          >
            {child.outstandingFees > 0 ? naira(child.outstandingFees) : "Cleared"}
          </dd>
        </div>
      </dl>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="report-card">Report card</TabsTrigger>
          <TabsTrigger value="attendance">Attendance</TabsTrigger>
          <TabsTrigger value="promotion">Promotion</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <section className="space-y-2">
            <h3 className="font-medium">Published results</h3>
            {myResults.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No published results are available yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {myResults.map((result) => (
                  <li
                    key={`${result.session}-${result.term}-${result.subject}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="min-w-0">
                      {result.subject} · {result.term} {result.session}
                    </span>
                    <span className="shrink-0 font-medium tabular-nums">
                      {result.score ?? "—"} {result.grade ? `· ${result.grade}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </TabsContent>

        <TabsContent value="report-card">
          <ReportCardTab childId={child.id} />
        </TabsContent>

        <TabsContent value="attendance">
          <AttendanceTab childId={child.id} />
        </TabsContent>

        <TabsContent value="promotion">
          <PromotionTab childId={child.id} />
        </TabsContent>
      </Tabs>

      <div className="mt-auto flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <Link to="/fees">Pay fees</Link>
        </Button>
      </div>
    </li>
  );
}

function ChildrenPage() {
  const query = useQuery({
    queryKey: ["children"],
    queryFn: () => listChildren({ pageSize: 100 }),
  });
  const resultsQuery = useQuery({
    queryKey: ["results", "my-published"],
    queryFn: getMyPublishedResults,
  });
  const children = query.data?.results ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My children"
        description="How each child is doing this term, and what you still owe the school."
      />

      {query.isError || resultsQuery.isError ? (
        <ErrorState
          onRetry={() => {
            void query.refetch();
            void resultsQuery.refetch();
          }}
        />
      ) : query.isPending || resultsQuery.isPending ? (
        <ListSkeleton />
      ) : children.length === 0 ? (
        <EmptyState
          title="No children linked to your account"
          description="Ask the school office to link your children to your phone number or email address."
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {children.map((child) => (
            <ChildCard key={child.id} child={child} results={resultsQuery.data ?? []} />
          ))}
        </ul>
      )}
    </div>
  );
}
