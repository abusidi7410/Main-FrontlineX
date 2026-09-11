import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { NewSheetDialog } from "@/features/results/new-sheet-dialog";
import { ScoresDialog } from "@/features/results/scores-dialog";
import { useSession } from "@/auth/session";
import { getResultSheets, updateResultSheetStatus } from "@/services/school.service";
import type { ResultSheet } from "@/types";

export const Route = createFileRoute("/_app/results")({
  head: () => ({
    meta: [
      { title: "Results — Frontline Nexus" },
      {
        name: "description",
        content: "Enter, submit, approve and publish termly results with a clear audit trail.",
      },
      { property: "og:title", content: "Results — Frontline Nexus" },
      { property: "og:description", content: "Enter, submit, approve and publish termly results." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ResultsPage,
});

function nextStatus(status: ResultSheet["status"]): ResultSheet["status"] | null {
  if (status === "draft") return "submitted";
  if (status === "submitted") return "under_review";
  if (status === "under_review") return "approved";
  if (status === "approved") return "published";
  return null;
}

function actionLabel(status: ResultSheet["status"]) {
  return status === "draft"
    ? "Submit for approval"
    : status === "submitted"
      ? "Start review"
      : status === "under_review"
        ? "Approve"
        : status === "approved"
          ? "Publish to parents"
          : "Published";
}

function ResultsPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["results"], queryFn: getResultSheets });
  const [openId, setOpenId] = useState<string | null>(null);
  const [scoresSheet, setScoresSheet] = useState<ResultSheet | null>(null);
  const [newSheetOpen, setNewSheetOpen] = useState(false);

  const advance = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ResultSheet["status"] }) =>
      updateResultSheetStatus(id, status),
    onSuccess: async (sheet) => {
      toast.success(
        `${sheet.className} ${sheet.subject} is now ${sheet.status.replace(/_/g, " ")}.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["results"] });
    },
    onError: () => toast.error("We couldn't update that result sheet. Please try again."),
  });

  return (
    <PermissionGate anyOf={["results.read", "results.write"]}>
      <div className="space-y-6">
        <PageHeader
          title="Results"
          description="Scores flow from the teacher to the principal, then to parents. Nothing is visible to parents until it is published."
          actions={
            <IfAllowed permission="results.write">
              <Button className="h-11" onClick={() => setNewSheetOpen(true)}>
                <Plus className="size-4" aria-hidden="true" /> New result sheet
              </Button>
            </IfAllowed>
          }
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <ul className="space-y-4">
            {query.data.map((sheet) => {
              const target = nextStatus(sheet.status);
              const allowed =
                sheet.status === "draft"
                  ? can("results.write")
                  : sheet.status === "approved"
                    ? can("results.publish")
                    : can("results.approve");
              const expanded = openId === sheet.id;
              return (
                <li key={sheet.id} className="fn-panel overflow-hidden">
                  <div className="flex flex-wrap items-center gap-3 border-b px-5 py-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">
                        {sheet.className} · {sheet.subject}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {sheet.term} · {sheet.rows.length} students
                      </p>
                    </div>
                    <StatusBadge status={sheet.status} />
                    <Button
                      variant="outline"
                      className="h-11"
                      onClick={() => setOpenId(expanded ? null : sheet.id)}
                    >
                      {expanded ? "Hide scores" : "View scores"}
                    </Button>
                    {can("results.write") && sheet.status === "draft" ? (
                      <Button
                        variant="outline"
                        className="h-11"
                        onClick={() => setScoresSheet(sheet)}
                      >
                        <Pencil className="size-4" aria-hidden="true" /> Enter scores
                      </Button>
                    ) : null}
                    {target && allowed ? (
                      <Button
                        className="h-11"
                        disabled={advance.isPending}
                        onClick={() => advance.mutate({ id: sheet.id, status: target })}
                      >
                        {actionLabel(sheet.status)}
                      </Button>
                    ) : null}
                  </div>
                  {expanded ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[36rem] text-left">
                        <caption className="sr-only">
                          {sheet.className} {sheet.subject} scores
                        </caption>
                        <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                          <tr>
                            <th scope="col" className="px-4 py-3 font-medium">
                              Student
                            </th>
                            <th scope="col" className="px-4 py-3 font-medium">
                              CA 1 (10)
                            </th>
                            <th scope="col" className="px-4 py-3 font-medium">
                              CA 2 (10)
                            </th>
                            <th scope="col" className="px-4 py-3 font-medium">
                              Assignment (20)
                            </th>
                            <th scope="col" className="px-4 py-3 font-medium">
                              Exam (60)
                            </th>
                            <th scope="col" className="px-4 py-3 font-medium">
                              Total
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {sheet.rows.slice(0, 12).map((row) => {
                            const total =
                              (row.ca1 ?? 0) +
                              (row.ca2 ?? 0) +
                              (row.assignment ?? 0) +
                              (row.exam ?? 0);
                            return (
                              <tr key={row.studentId}>
                                <td className="px-4 py-3">{row.studentName}</td>
                                <td className="px-4 py-3 tabular-nums">{row.ca1 ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.ca2 ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.assignment ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.exam ?? "—"}</td>
                                <td className="px-4 py-3 font-medium tabular-nums">{total}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}

        <NewSheetDialog open={newSheetOpen} onOpenChange={setNewSheetOpen} />

        <ScoresDialog
          sheet={scoresSheet}
          open={scoresSheet !== null}
          onOpenChange={(open) => {
            if (!open) setScoresSheet(null);
          }}
        />
      </div>
    </PermissionGate>
  );
}
