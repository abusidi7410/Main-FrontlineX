import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, ArrowLeft, ArrowLeftRight, Pencil, UserCheck, UserMinus } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { IfAllowed } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TransferStudentDialog } from "@/features/students/transfer-student-dialog";
import { dateFmt, naira, percent } from "@/lib/format";
import { getStudent, reinstateStudent, suspendStudent } from "@/services/students.service";

export const Route = createFileRoute("/_app/students/$studentId")({
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
            <li key={entry.session} className="flex flex-wrap items-center gap-x-4 px-5 py-4">
              <p className="min-w-0 flex-1 font-medium">{entry.session}</p>
              <p className="text-muted-foreground">{entry.className}</p>
              <p className="text-muted-foreground">{entry.outcome}</p>
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
