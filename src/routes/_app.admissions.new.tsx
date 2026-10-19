import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/api/client";
import { getAcademicStructure } from "@/services/academics.service";
import {
  createAdmissionApplication,
  submitAdmissionApplication,
} from "@/services/admissions.service";
import {
  AdmissionWizard,
  EMPTY_ADMISSION,
  toAdmissionInput,
  useAdmissionSettings,
  type AdmissionFormValues,
} from "@/features/admissions/admission-wizard";
import type { AdmissionApplication } from "@/types";

export const Route = createFileRoute("/_app/admissions/new")({
  head: () => ({
    meta: [
      { title: "New admission application — Frontline Nexus" },
      {
        name: "description",
        content: "Take a complete admission application and submit it for review.",
      },
      { property: "og:title", content: "New admission application — Frontline Nexus" },
      {
        property: "og:description",
        content: "Take a complete admission application and submit it for review.",
      },
      { property: "robots", content: "noindex" },
    ],
  }),
  component: NewAdmissionPage,
});

function isDuplicateConflict(error: unknown): boolean {
  if (!(error instanceof ApiRequestError) || error.status !== 400) return false;
  const fieldErrors = error.fieldErrors ?? {};
  return "duplicateApplicationId" in fieldErrors || "duplicateStudentId" in fieldErrors;
}

function NewAdmissionPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settings = useAdmissionSettings();
  const academics = useQuery({ queryKey: ["academics"], queryFn: getAcademicStructure });
  const [serverErrors, setServerErrors] = useState<Record<string, string> | undefined>();
  const [duplicateDraft, setDuplicateDraft] = useState<AdmissionApplication | null>(null);

  const openApplication = async (id: string) => {
    await queryClient.invalidateQueries({ queryKey: ["admissions"] });
    await queryClient.invalidateQueries({ queryKey: ["admission-stats"] });
    void navigate({ to: "/admissions/$applicationId", params: { applicationId: id } });
  };

  const create = useMutation({
    mutationFn: async (values: AdmissionFormValues) => {
      const draft = await createAdmissionApplication(
        toAdmissionInput(values, academics.data?.classIds ?? {}, academics.data?.sessionId ?? null),
      );
      try {
        const submitted = await submitAdmissionApplication(draft.id);
        return { application: submitted, duplicate: false };
      } catch (error) {
        if (isDuplicateConflict(error)) return { application: draft, duplicate: true };
        throw error;
      }
    },
    onSuccess: async ({ application, duplicate }) => {
      if (duplicate) {
        setDuplicateDraft(application);
        return;
      }
      toast.success(
        `${application.firstName} ${application.lastName}'s application was submitted for review.`,
      );
      await openApplication(application.id);
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 400 && error.fieldErrors) {
        setServerErrors(error.fieldErrors);
        toast.error("Some details still need attention before this can be submitted.");
        return;
      }
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "We couldn't save this application. Please try again.",
      );
    },
  });

  const forceSubmit = useMutation({
    mutationFn: (id: string) => submitAdmissionApplication(id, { allowDuplicate: true }),
    onSuccess: async (application) => {
      setDuplicateDraft(null);
      toast.success(`${application.firstName} ${application.lastName}'s application submitted.`);
      await openApplication(application.id);
    },
    onError: (error) => {
      setDuplicateDraft(null);
      toast.error(
        error instanceof ApiRequestError ? error.message : "That submission failed. Try again.",
      );
    },
  });

  if (settings.isError || academics.isError) {
    return (
      <ErrorState
        message="We couldn't load the admission requirements for your school."
        onRetry={() => {
          void settings.refetch();
          void academics.refetch();
        }}
      />
    );
  }
  if (settings.isPending || academics.isPending || !settings.data) {
    return <CardsSkeleton count={2} />;
  }

  return (
    <PermissionGate permission="admissions.write">
      <div className="mx-auto max-w-4xl space-y-6">
        <PageHeader
          title="New admission application"
          description="Complete each section, then submit the application for review. You can attach documents on the application page."
        />
        <AdmissionWizard
          settings={settings.data}
          defaultValues={EMPTY_ADMISSION}
          submitLabel="Submit application"
          isPending={create.isPending}
          serverErrors={serverErrors}
          onSubmit={(values) => {
            setServerErrors(undefined);
            create.mutate(values);
          }}
          onCancel={
            <Button asChild type="button" variant="outline" className="h-12">
              <Link to="/admissions">Cancel</Link>
            </Button>
          }
        />

        <ConfirmDialog
          open={duplicateDraft !== null}
          onOpenChange={(open) => {
            if (!open) setDuplicateDraft(null);
          }}
          title="A similar application already exists"
          description="A child with the same name and date of birth is already recorded. If this is genuinely a different child, you can submit anyway."
          confirmLabel="Submit anyway"
          onConfirm={() => {
            if (duplicateDraft) forceSubmit.mutate(duplicateDraft.id);
          }}
        />
      </div>
    </PermissionGate>
  );
}
