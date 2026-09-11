import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { createStaff } from "@/services/staff.service";
import { StaffForm, toStaffInput, type StaffValues } from "@/features/staff/staff-form";

export const Route = createFileRoute("/_app/staff/new")({
  head: () => ({
    meta: [
      { title: "Add a staff member — Frontline Nexus" },
      {
        name: "description",
        content: "Register a new teacher or administrator with their role and contact details.",
      },
      { property: "og:title", content: "Add a staff member — Frontline Nexus" },
      {
        property: "og:description",
        content: "Register a new teacher or administrator with their role and contact details.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: NewStaffPage,
});

function NewStaffPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (values: StaffValues) => createStaff(toStaffInput(values)),
    onSuccess: async () => {
      toast.success("The staff member has been added.");
      await queryClient.invalidateQueries({ queryKey: ["staff"] });
      void navigate({ to: "/staff" });
    },
    onError: () =>
      toast.error("We couldn't save this staff member. Please check the details and try again."),
  });

  return (
    <PermissionGate permission="staff.write">
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader
          title="Add a staff member"
          description="Their account is created and they'll be invited to the platform."
        />

        <StaffForm
          defaultValues={{
            fullName: "",
            email: "",
            phone: "",
            role: "teacher",
            subjects: "",
            classes: "",
          }}
          submitLabel="Save staff member"
          isPending={mutation.isPending}
          onSubmit={(values) => mutation.mutate(values)}
          cancelLink={
            <Button asChild type="button" variant="outline" className="h-12">
              <Link to="/staff">Cancel</Link>
            </Button>
          }
        />
      </div>
    </PermissionGate>
  );
}
