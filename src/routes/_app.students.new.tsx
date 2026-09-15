import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { ARMS, CLASSES } from "@/constants/reference";
import { createStudent } from "@/services/students.service";
import { StudentForm } from "@/features/students/student-form";

export const Route = createFileRoute("/_app/students/new")({
  head: () => ({
    meta: [
      { title: "Add a student — Frontline Nexus" },
      {
        name: "description",
        content: "Register a new student with class, guardian and admission details.",
      },
      { property: "og:title", content: "Add a student — Frontline Nexus" },
      {
        property: "og:description",
        content: "Register a new student with class, guardian and admission details.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: NewStudentPage,
});

function NewStudentPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createStudent,
    onSuccess: async (student) => {
      toast.success(
        `${student.firstName} ${student.lastName} has been added to ${student.className}${student.arm}.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["students"] });
      void navigate({ to: "/students" });
    },
    onError: () =>
      toast.error("We couldn't save this student. Please check the details and try again."),
  });

  return (
    <PermissionGate permission="students.write">
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader
          title="Add a student"
          description="Only the essentials now — you can complete the full profile later."
        />

        <StudentForm
          defaultValues={{
            firstName: "",
            lastName: "",
            admissionNumber: "",
            gender: "male",
            dateOfBirth: "",
            className: CLASSES[0] ?? "",
            arm: ARMS[0] ?? "",
            guardianName: "",
            guardianPhone: "",
          }}
          submitLabel="Save student"
          isPending={mutation.isPending}
          onSubmit={(values) => mutation.mutate(values)}
          cancelLink={
            <Button asChild type="button" variant="outline" className="h-12">
              <Link to="/students">Cancel</Link>
            </Button>
          }
        />
      </div>
    </PermissionGate>
  );
}