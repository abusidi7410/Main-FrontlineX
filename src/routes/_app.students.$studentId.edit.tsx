import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { getStudent, updateStudent } from "@/services/students.service";
import { StudentForm, type StudentValues } from "@/features/students/student-form";

export const Route = createFileRoute("/_app/students/$studentId/edit")({
  head: () => ({
    meta: [
      { title: "Edit student — Frontline Nexus" },
      {
        name: "description",
        content: "Update a student's personal, class and guardian details.",
      },
      { property: "og:title", content: "Edit student — Frontline Nexus" },
      {
        property: "og:description",
        content: "Update a student's personal, class and guardian details.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: EditStudentPage,
});

function EditStudentPage() {
  const { studentId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["student", studentId],
    queryFn: () => getStudent(studentId),
  });

  const mutation = useMutation({
    mutationFn: (values: StudentValues) => updateStudent(studentId, values),
    onSuccess: async (student) => {
      toast.success(`${student.firstName} ${student.lastName}'s details have been updated.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["student", studentId] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
      ]);
      void navigate({ to: "/students/$studentId", params: { studentId } });
    },
    onError: () =>
      toast.error("We couldn't save the changes. Please check the details and try again."),
  });

  if (query.isError) {
    return (
      <ErrorState
        message="We couldn't find that student record."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <CardsSkeleton count={2} />;

  const student = query.data;

  return (
    <PermissionGate permission="students.write">
      <div className="space-y-6">
        <Link
          to="/students/$studentId"
          params={{ studentId }}
          className="inline-flex items-center gap-2 font-medium text-primary hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden="true" /> Back to student profile
        </Link>

        <div className="mx-auto max-w-3xl space-y-6">
          <PageHeader
            title="Edit student"
            description={`${student.firstName} ${student.lastName} · ${student.admissionNumber}`}
          />

          <StudentForm
            key={student.id}
            defaultValues={{
              firstName: student.firstName,
              lastName: student.lastName,
              admissionNumber: student.admissionNumber,
              gender: student.gender,
              dateOfBirth: student.dateOfBirth,
              className: student.className,
              arm: student.arm,
              guardianName: student.guardianName,
              guardianPhone: student.guardianPhone,
            }}
            submitLabel="Save changes"
            isPending={mutation.isPending}
            onSubmit={(values) => mutation.mutate(values)}
            cancelLink={
              <Button asChild type="button" variant="outline" className="h-12">
                <Link to="/students/$studentId" params={{ studentId }}>
                  Cancel
                </Link>
              </Button>
            }
          />
        </div>
      </div>
    </PermissionGate>
  );
}