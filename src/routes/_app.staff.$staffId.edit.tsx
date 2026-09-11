import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { getStaffMember, updateStaff } from "@/services/staff.service";
import {
  StaffForm,
  toStaffFormValues,
  toStaffInput,
  type StaffValues,
} from "@/features/staff/staff-form";

export const Route = createFileRoute("/_app/staff/$staffId/edit")({
  head: () => ({
    meta: [
      { title: "Edit staff member — Frontline Nexus" },
      {
        name: "description",
        content: "Update a staff member's role and contact details.",
      },
      { property: "og:title", content: "Edit staff member — Frontline Nexus" },
      {
        property: "og:description",
        content: "Update a staff member's role and contact details.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: EditStaffPage,
});

function EditStaffPage() {
  const { staffId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["staff", staffId],
    queryFn: () => getStaffMember(staffId),
  });

  const mutation = useMutation({
    mutationFn: (values: StaffValues) => updateStaff(staffId, toStaffInput(values)),
    onSuccess: async (member) => {
      toast.success(`${member.fullName}'s details have been updated.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["staff", staffId] }),
        queryClient.invalidateQueries({ queryKey: ["staff"] }),
      ]);
      void navigate({ to: "/staff/$staffId", params: { staffId } });
    },
    onError: () =>
      toast.error("We couldn't save the changes. Please check the details and try again."),
  });

  if (query.isError) {
    return (
      <ErrorState
        message="We couldn't find that staff record."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <CardsSkeleton count={2} />;

  const member = query.data;

  return (
    <PermissionGate permission="staff.write">
      <div className="space-y-6">
        <Link
          to="/staff/$staffId"
          params={{ staffId }}
          className="inline-flex items-center gap-2 font-medium text-primary hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden="true" /> Back to staff profile
        </Link>

        <div className="mx-auto max-w-3xl space-y-6">
          <PageHeader
            title="Edit staff member"
            description={`${member.fullName} · ${member.email}`}
          />

          <StaffForm
            key={member.id}
            defaultValues={toStaffFormValues(member)}
            submitLabel="Save changes"
            isPending={mutation.isPending}
            onSubmit={(values) => mutation.mutate(values)}
            cancelLink={
              <Button asChild type="button" variant="outline" className="h-12">
                <Link to="/staff/$staffId" params={{ staffId }}>
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
