import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { naira, percent } from "@/lib/format";
import { getMyPublishedResults } from "@/services/school.service";
import { listStudents } from "@/services/students.service";

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

function ChildrenPage() {
  const query = useQuery({ queryKey: ["children"], queryFn: () => listStudents({ pageSize: 3 }) });
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
            <li key={child.id} className="fn-panel flex flex-col gap-4 p-5">
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

              <section className="space-y-2 border-t pt-4">
                <h3 className="font-medium">Published results</h3>
                {(resultsQuery.data ?? []).filter((result) => result.studentId === child.id)
                  .length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No published results are available yet.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {(resultsQuery.data ?? [])
                      .filter((result) => result.studentId === child.id)
                      .map((result) => (
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

              <div className="mt-auto flex flex-wrap gap-2">
                <Button asChild size="sm" variant="outline">
                  <Link to="/fees">Pay fees</Link>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
