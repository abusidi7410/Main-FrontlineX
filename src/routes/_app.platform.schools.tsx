import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebounced } from "@/hooks/use-debounced";
import { dateFmt, naira, numberFmt } from "@/lib/format";
import { tierById } from "@/constants/plans";
import { listPlatformSchools, setSchoolStatus } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/schools")({
  head: () => ({
    meta: [
      { title: "Schools — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Every school on Frontline Nexus with plan, size and account status.",
      },
      { property: "og:title", content: "Schools — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Every school on Frontline Nexus with plan, size and account status.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSchoolsPage,
});

const STATUSES = ["active", "trial", "grace", "pending_payment", "suspended"] as const;

function PlatformSchoolsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const debounced = useDebounced(search, 300);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["platform", "schools", debounced, status],
    queryFn: () => listPlatformSchools(debounced, status === "all" ? "" : status),
  });

  const mutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: (typeof STATUSES)[number] }) =>
      setSchoolStatus(id, next),
    onSuccess: (school) => {
      toast.success(`${school.name} is now ${school.status.replace("_", " ")}`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    },
    onError: () => toast.error("We couldn't update that school. Please try again."),
  });

  const schools = query.data ?? [];

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Schools"
          description="Search, review and change the account status of any school on the platform."
        />

        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            className="h-11"
            placeholder="Search by school name or state"
            aria-label="Search schools"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-11 sm:w-56" aria-label="Filter by status">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s.replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : schools.length === 0 ? (
          <EmptyState
            title="No schools match your filters"
            description="Try another name, state or status."
          />
        ) : (
          <ul className="fn-panel divide-y">
            {schools.map((school) => (
              <li key={school.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{school.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {school.state} · {numberFmt(school.students)} students ·{" "}
                    {tierById(school.tierId).label} · joined {dateFmt(school.createdAt)}
                  </p>
                </div>
                <span className="tabular-nums text-sm text-muted-foreground">
                  {naira(school.mrr)}/mo
                </span>
                <StatusBadge status={school.status} />
                {school.status === "suspended" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate({ id: school.id, next: "active" })}
                  >
                    Reactivate
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate({ id: school.id, next: "suspended" })}
                  >
                    Suspend
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}
