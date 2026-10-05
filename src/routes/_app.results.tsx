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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { NewSheetDialog } from "@/features/results/new-sheet-dialog";
import { ScoresDialog } from "@/features/results/scores-dialog";
import { useSession } from "@/auth/session";
import {
  getResultSheet,
  getResultSheetPage,
  releaseResultCorrection,
  requestResultCorrection,
  updateResultSheetStatus,
} from "@/services/school.service";
import type { ResultSheetStatus } from "@/types";
import { invalidateEnrollmentQueries } from "@/lib/query-invalidation";

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

function nextStatus(status: ResultSheetStatus): ResultSheetStatus | null {
  if (status === "draft") return "submitted";
  if (status === "submitted") return "under_review";
  if (status === "under_review") return "approved";
  if (status === "approved") return "published";
  if (status === "published") return "locked";
  return null;
}

function actionLabel(status: ResultSheetStatus) {
  return status === "draft"
    ? "Submit for approval"
    : status === "submitted"
      ? "Start review"
      : status === "under_review"
        ? "Approve"
        : status === "approved"
          ? "Publish to parents"
          : status === "published"
            ? "Lock results"
            : "Locked";
}

function ResultsPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["results", page],
    queryFn: () => getResultSheetPage(page),
  });
  const [openId, setOpenId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [correctionId, setCorrectionId] = useState<string | null>(null);
  const [correctionReason, setCorrectionReason] = useState("");
  const [newSheetOpen, setNewSheetOpen] = useState(false);
  const detailId = editingId ?? openId;
  const detailQuery = useQuery({
    queryKey: ["result-sheet", detailId],
    queryFn: () => getResultSheet(detailId!),
    enabled: detailId !== null,
  });

  const advance = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ResultSheetStatus }) =>
      updateResultSheetStatus(id, status),
    onSuccess: async (sheet) => {
      toast.success(
        `${sheet.className} ${sheet.subject} is now ${sheet.status.replace(/_/g, " ")}.`,
      );
      await invalidateEnrollmentQueries(queryClient, [["result-sheet", sheet.id]]);
    },
    onError: () => toast.error("We couldn't update that result sheet. Please try again."),
  });
  const correction = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      reason === undefined ? releaseResultCorrection(id) : requestResultCorrection(id, reason),
    onSuccess: async (sheet) => {
      toast.success(
        sheet.status === "draft"
          ? "Correction approved. The sheet is editable and must be reviewed again."
          : "Correction request recorded.",
      );
      setCorrectionId(null);
      setCorrectionReason("");
      await invalidateEnrollmentQueries(queryClient, [["result-sheet", sheet.id]]);
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Could not update the correction."),
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
            {query.data.results.map((sheet) => {
              const target = nextStatus(sheet.status);
              const allowed =
                sheet.status === "draft"
                  ? can("results.write")
                  : sheet.status === "approved" || sheet.status === "published"
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
                        {sheet.term} · {sheet.studentCount} students
                      </p>
                    </div>
                    <StatusBadge status={sheet.status} />
                    <Button
                      variant="outline"
                      className="h-11"
                      onClick={() => {
                        setEditingId(null);
                        setOpenId(expanded ? null : sheet.id);
                      }}
                    >
                      {expanded ? "Hide scores" : "View scores"}
                    </Button>
                    {can("results.write") && sheet.status === "draft" ? (
                      <Button
                        variant="outline"
                        className="h-11"
                        onClick={() => {
                          setOpenId(sheet.id);
                          setEditingId(sheet.id);
                        }}
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
                    {sheet.status === "locked" &&
                    sheet.correctionRequested &&
                    can("results.publish") ? (
                      <Button
                        className="h-11"
                        variant="outline"
                        disabled={correction.isPending}
                        onClick={() => correction.mutate({ id: sheet.id })}
                      >
                        Approve correction
                      </Button>
                    ) : null}
                    {sheet.status === "locked" &&
                    !sheet.correctionRequested &&
                    can("results.write") ? (
                      <Button
                        className="h-11"
                        variant="outline"
                        onClick={() => setCorrectionId(sheet.id)}
                      >
                        Request correction
                      </Button>
                    ) : null}
                  </div>
                  {expanded && detailQuery.isPending ? (
                    <p className="px-5 py-4 text-sm text-muted-foreground">Loading scores…</p>
                  ) : null}
                  {expanded && detailQuery.isError ? (
                    <ErrorState onRetry={() => void detailQuery.refetch()} />
                  ) : null}
                  {expanded && detailQuery.data?.id === sheet.id ? (
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
                          {detailQuery.data.rows.map((row) => {
                            return (
                              <tr key={row.studentId}>
                                <td className="px-4 py-3">{row.studentName}</td>
                                <td className="px-4 py-3 tabular-nums">{row.ca1 ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.ca2 ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.assignment ?? "—"}</td>
                                <td className="px-4 py-3 tabular-nums">{row.exam ?? "—"}</td>
                                <td className="px-4 py-3 font-medium tabular-nums">
                                  {row.score ?? "—"} {row.grade ? `(${row.grade})` : ""}
                                </td>
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
        {query.data && query.data.totalPages > 1 ? (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Page {query.data.page} of {query.data.totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="h-10"
                disabled={page <= 1 || query.isFetching}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                className="h-10"
                disabled={page >= query.data.totalPages || query.isFetching}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}

        <NewSheetDialog open={newSheetOpen} onOpenChange={setNewSheetOpen} />

        <ScoresDialog
          sheet={editingId && detailQuery.data?.id === editingId ? detailQuery.data : null}
          open={editingId !== null && detailQuery.data?.id === editingId}
          onOpenChange={(open) => {
            if (!open) setEditingId(null);
          }}
        />
        <Dialog
          open={correctionId !== null}
          onOpenChange={(open) => {
            if (!open) {
              setCorrectionId(null);
              setCorrectionReason("");
            }
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Request a result correction</DialogTitle>
              <DialogDescription>
                Explain what needs to change. A results publisher must approve the request before
                scores can be edited.
              </DialogDescription>
            </DialogHeader>
            <Textarea
              value={correctionReason}
              onChange={(event) => setCorrectionReason(event.target.value)}
              maxLength={255}
              placeholder="Reason for the correction"
              aria-label="Reason for the correction"
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setCorrectionId(null)}>
                Cancel
              </Button>
              <Button
                disabled={
                  !correctionReason.trim() ||
                  correctionReason.length > 255 ||
                  correction.isPending ||
                  correctionId === null
                }
                onClick={() =>
                  correctionId &&
                  correction.mutate({ id: correctionId, reason: correctionReason.trim() })
                }
              >
                {correction.isPending ? "Submitting…" : "Submit request"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </PermissionGate>
  );
}
