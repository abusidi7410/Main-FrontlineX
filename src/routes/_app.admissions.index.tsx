import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ClipboardList, Plus, Search, Trash2, UserPlus, UserCheck } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { TablePager } from "@/components/common/table-pager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiRequestError } from "@/api/client";
import { useSession } from "@/auth/session";
import { useDebounced } from "@/hooks/use-debounced";
import { dateFmt } from "@/lib/format";
import {
  deleteAdmissionApplication,
  getAdmissionStats,
  listAdmissionApplications,
} from "@/services/admissions.service";
import { ADMISSION_DOCUMENT_LABELS, type AdmissionStatus } from "@/types";

export const Route = createFileRoute("/_app/admissions/")({
  head: () => ({
    meta: [
      { title: "Admissions — Frontline Nexus" },
      {
        name: "description",
        content:
          "Review admission applications, verify documents and admit new students into the school.",
      },
      { property: "og:title", content: "Admissions — Frontline Nexus" },
      {
        property: "og:description",
        content: "Review applications, verify documents and admit new students.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AdmissionsPage,
});

const TABS: { value: AdmissionStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "submitted", label: "Submitted" },
  { value: "under_review", label: "Under review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function AdmissionsPage() {
  const { can } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<AdmissionStatus | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebounced(search);

  const stats = useQuery({ queryKey: ["admission-stats"], queryFn: getAdmissionStats });
  const applications = useQuery({
    queryKey: ["admissions", debouncedSearch, tab, page],
    queryFn: () =>
      listAdmissionApplications({ search: debouncedSearch, status: tab, page, pageSize: 25 }),
  });

  const remove = useMutation({
    mutationFn: deleteAdmissionApplication,
    onSuccess: async () => {
      toast.success("Draft application deleted.");
      await queryClient.invalidateQueries({ queryKey: ["admissions"] });
      await queryClient.invalidateQueries({ queryKey: ["admission-stats"] });
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError ? error.message : "That draft could not be deleted.",
      );
    },
  });

  return (
    <PermissionGate permission="admissions.read">
      <div className="space-y-6">
        <PageHeader
          title="Admissions"
          description="Take applications, verify documents and admit new students in one place."
          actions={
            can("admissions.write") ? (
              <Button asChild className="h-11">
                <Link to="/admissions/new">
                  <Plus className="size-4" aria-hidden="true" />
                  New application
                </Link>
              </Button>
            ) : null
          }
        />

        {stats.data ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Total applications"
              value={stats.data.total}
              icon={<ClipboardList className="size-5" aria-hidden="true" />}
            />
            <StatCard
              label="Needs review"
              value={stats.data.needsReview}
              tone={stats.data.needsReview > 0 ? "warning" : "default"}
              hint="Submitted or under review"
              icon={<UserPlus className="size-5" aria-hidden="true" />}
            />
            <StatCard
              label="Admitted"
              value={stats.data.approved}
              tone="success"
              hint={`${stats.data.approvedThisMonth} this month`}
              icon={<UserCheck className="size-5" aria-hidden="true" />}
            />
            <StatCard
              label="Drafts in progress"
              value={stats.data.draft}
              hint="Not yet submitted"
            />
          </div>
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Tabs
            value={tab || "all"}
            onValueChange={(value) => {
              setTab(value === "all" ? "" : (value as AdmissionStatus));
              setPage(1);
            }}
          >
            <TabsList className="flex-wrap">
              {TABS.map((item) => (
                <TabsTrigger key={item.value || "all"} value={item.value || "all"}>
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className="relative sm:w-72">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search name, guardian or phone"
              aria-label="Search applications"
              className="h-11 pl-9"
            />
          </div>
        </div>

        {applications.isError ? (
          <ErrorState onRetry={() => void applications.refetch()} />
        ) : applications.isPending ? (
          <ListSkeleton />
        ) : applications.data.results.length === 0 ? (
          <EmptyState
            title="No applications here yet"
            description={
              search
                ? "No application matches that search. Try a different name or phone number."
                : "Start a new application and it will appear here as a draft until it is submitted."
            }
            action={
              can("admissions.write") ? (
                <Button asChild>
                  <Link to="/admissions/new">New application</Link>
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="fn-panel divide-y">
            {applications.data.results.map((application) => (
              <li key={application.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <Link
                    to="/admissions/$applicationId"
                    params={{ applicationId: application.id }}
                    className="font-medium hover:underline"
                  >
                    {[application.firstName, application.middleName, application.lastName]
                      .filter(Boolean)
                      .join(" ")}
                  </Link>
                  <p className="text-sm text-muted-foreground">
                    {application.className || "No class chosen"}
                    {application.guardianName ? ` · ${application.guardianName}` : ""}
                    {application.guardianPhone ? ` · ${application.guardianPhone}` : ""}
                    {application.submittedAt
                      ? ` · submitted ${dateFmt(application.submittedAt)}`
                      : ` · saved ${dateFmt(application.lastSavedAt)}`}
                  </p>
                  {application.missingDocuments.length > 0 && application.status !== "draft" ? (
                    <p className="mt-1 text-sm text-warning">
                      Missing:{" "}
                      {application.missingDocuments
                        .map((category) => ADMISSION_DOCUMENT_LABELS[category])
                        .join(", ")}
                    </p>
                  ) : null}
                </div>
                <StatusBadge status={application.status} />
                {application.admissionNumber ? (
                  <span className="text-sm text-muted-foreground">
                    {application.admissionNumber}
                  </span>
                ) : null}
                <Button asChild variant="outline" className="h-11">
                  <Link to="/admissions/$applicationId" params={{ applicationId: application.id }}>
                    Open
                  </Link>
                </Button>
                {application.status === "draft" && can("admissions.write") ? (
                  <ConfirmDialog
                    title="Delete this draft?"
                    description="The draft and any documents attached to it will be discarded. This cannot be undone."
                    confirmLabel="Delete draft"
                    destructive
                    trigger={
                      <Button
                        variant="ghost"
                        className="h-11 text-destructive"
                        aria-label="Delete draft"
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                      </Button>
                    }
                    onConfirm={() => remove.mutate(application.id)}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {applications.data ? (
          <TablePager
            page={applications.data.page}
            pageSize={applications.data.pageSize}
            count={applications.data.count}
            onPageChange={setPage}
            itemLabel="applications"
            disabled={applications.isFetching}
          />
        ) : null}

        <p className="text-sm text-muted-foreground">
          Admitted applicants appear on the{" "}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => void navigate({ to: "/students" })}
          >
            Students
          </button>{" "}
          page with an invoice raised for the registration fee.
        </p>
      </div>
    </PermissionGate>
  );
}
