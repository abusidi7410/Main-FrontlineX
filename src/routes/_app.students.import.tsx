import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { tierById } from "@/constants/plans";
import { numberFmt } from "@/lib/format";
import { getSubscription } from "@/services/school.service";
import { analyseImportFile, commitImport, type ImportAnalysis } from "@/services/students.service";

export const Route = createFileRoute("/_app/students/import")({
  head: () => ({
    meta: [
      { title: "Import students — Frontline Nexus" },
      {
        name: "description",
        content:
          "Bulk import your student roster from a CSV file with validation before anything is saved.",
      },
      { property: "og:title", content: "Import students — Frontline Nexus" },
      {
        property: "og:description",
        content: "Bulk import your student roster from a CSV file with validation.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ImportStudentsPage,
});

const TEMPLATE = "first_name,last_name,admission_number,class,guardian_phone\n";

function ImportStudentsPage() {
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const queryClient = useQueryClient();
  const subscription = useQuery({ queryKey: ["subscription"], queryFn: getSubscription });
  const tier = subscription.data ? tierById(subscription.data.tierId) : null;
  const allowed = tier?.maxStudents ?? 5000;

  const analyse = useMutation({
    mutationFn: (file: File) =>
      analyseImportFile(file, subscription.data?.activeStudents ?? 0, allowed),
    onSuccess: setAnalysis,
    onError: () =>
      toast.error("We couldn't read that file. Please upload a CSV that matches the template."),
  });

  const commit = useMutation({
    mutationFn: commitImport,
    onSuccess: async (result) => {
      toast.success(`${result.imported} students imported successfully.`);
      setAnalysis(null);
      await queryClient.invalidateQueries({ queryKey: ["students"] });
    },
    onError: () =>
      toast.error("The import didn't complete. No students were added — please try again."),
  });

  return (
    <PermissionGate permission="students.import">
      <div className="space-y-6">
        <PageHeader
          title="Import students"
          description="Upload a CSV of your roster. We check every row for duplicates and missing information before anything is saved."
          actions={
            <Button asChild variant="outline" className="h-11">
              <a
                href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`}
                download="frontline-nexus-students.csv"
              >
                Download template
              </a>
            </Button>
          }
        />

        <div className="fn-panel space-y-3 p-5">
          <Label htmlFor="csv">CSV file</Label>
          <Input
            id="csv"
            type="file"
            accept=".csv,text/csv"
            className="h-12"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) analyse.mutate(file);
            }}
          />
          <p className="text-sm text-muted-foreground">
            Required columns: first_name, last_name, admission_number, class, guardian_phone.
          </p>
          {analyse.isPending ? (
            <p className="text-sm text-muted-foreground">Checking your file…</p>
          ) : null}
        </div>

        {analysis ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label="Rows found"
                value={numberFmt(analysis.total)}
                hint={analysis.fileName}
              />
              <StatCard label="Ready to import" value={numberFmt(analysis.valid)} tone="success" />
              <StatCard
                label="Duplicates"
                value={numberFmt(analysis.duplicates)}
                tone="warning"
                hint="Admission number already exists"
              />
              <StatCard
                label="Missing information"
                value={numberFmt(analysis.missingFields)}
                tone="warning"
              />
            </div>

            {analysis.capacity.exceeds ? (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4"
              >
                <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden="true" />
                <p className="text-sm">
                  This import would take you to {numberFmt(analysis.capacity.afterImport)} students,
                  above your plan limit of {numberFmt(analysis.capacity.allowed)}. Upgrade your plan
                  to continue.{" "}
                  <Link to="/subscription" className="font-medium text-primary hover:underline">
                    View plans
                  </Link>
                </p>
              </div>
            ) : null}

            <div className="fn-panel overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left">
                <caption className="sr-only">Rows detected in your file</caption>
                <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Row
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Name
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Admission no.
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Class
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Issues
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {analysis.rows.slice(0, 25).map((row) => (
                    <tr
                      key={row.rowNumber}
                      className={row.issues.length ? "bg-warning-soft/40" : undefined}
                    >
                      <td className="px-4 py-3 tabular-nums">{row.rowNumber}</td>
                      <td className="px-4 py-3">
                        {row.firstName} {row.lastName}
                      </td>
                      <td className="px-4 py-3">{row.admissionNumber || "—"}</td>
                      <td className="px-4 py-3">{row.className || "—"}</td>
                      <td className="px-4 py-3 text-sm">{row.issues.join(", ") || "Ready"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                className="h-12 text-base"
                disabled={analysis.valid === 0 || analysis.capacity.exceeds || commit.isPending}
                onClick={() => commit.mutate(analysis)}
              >
                <FileSpreadsheet className="size-4" aria-hidden="true" />
                {commit.isPending ? "Importing…" : `Import ${numberFmt(analysis.valid)} students`}
              </Button>
              <Button variant="outline" className="h-12" onClick={() => setAnalysis(null)}>
                Choose a different file
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </PermissionGate>
  );
}
