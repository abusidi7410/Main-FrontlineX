import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, BadgeCheck, Ban, Pencil, ShieldCheck, Undo2 } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiRequestError } from "@/api/client";
import { useSession } from "@/auth/session";
import { getAcademicStructure } from "@/services/academics.service";
import { dateFmt, dateTimeFmt, naira, titleCase } from "@/lib/format";
import {
  approveAdmissionApplication,
  getAdmissionApplication,
  rejectAdmissionApplication,
  startAdmissionReview,
  submitAdmissionApplication,
  updateAdmissionApplication,
  withdrawAdmissionApplication,
} from "@/services/admissions.service";
import {
  AdmissionWizard,
  useAdmissionSettings,
  toAdmissionInput,
  toFormValues,
  type AdmissionFormValues,
} from "@/features/admissions/admission-wizard";
import { DocumentPanel } from "@/features/admissions/document-panel";
import type { AdmissionApplication } from "@/types";

export const Route = createFileRoute("/_app/admissions/$applicationId")({
  head: () => ({
    meta: [
      { title: "Application — Frontline Nexus" },
      {
        name: "description",
        content: "Review an admission application, verify its documents and admit the student.",
      },
      { property: "og:title", content: "Application — Frontline Nexus" },
      {
        property: "og:description",
        content: "Review an application, verify documents and admit the student.",
      },
      { property: "robots", content: "noindex" },
    ],
  }),
  component: AdmissionDetailPage,
});

function fullName(application: AdmissionApplication): string {
  return [application.firstName, application.middleName, application.lastName]
    .filter(Boolean)
    .join(" ");
}

function AdmissionDetailPage() {
  const { applicationId } = Route.useParams();
  const { can } = useSession();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const settings = useAdmissionSettings();
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [approving, setApproving] = useState(false);
  const [admissionNumber, setAdmissionNumber] = useState("");
  const [pendingDuplicate, setPendingDuplicate] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string> | undefined>();

  const application = useQuery({
    queryKey: ["admission", applicationId],
    queryFn: () => getAdmissionApplication(applicationId),
  });
  const academics = useQuery({ queryKey: ["academics"], queryFn: getAcademicStructure });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admission", applicationId] });
    await queryClient.invalidateQueries({ queryKey: ["admissions"] });
    await queryClient.invalidateQueries({ queryKey: ["admission-stats"] });
  };

  const showError = (error: unknown, fallback: string) =>
    toast.error(error instanceof ApiRequestError ? error.message : fallback);

  const save = useMutation({
    mutationFn: (values: AdmissionFormValues) => {
      const classIds = academics.data?.classIds ?? {};
      return updateAdmissionApplication(applicationId, {
        ...toAdmissionInput(values, classIds, academics.data?.sessionId ?? null),
        classId: classIds[values.className] ?? application.data?.classId ?? null,
      });
    },
    onSuccess: async () => {
      toast.success("Draft saved.");
      setEditing(false);
      setServerErrors(undefined);
      await invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.fieldErrors) {
        setServerErrors(error.fieldErrors);
      }
      showError(error, "We couldn't save these changes.");
    },
  });

  const submit = useMutation({
    mutationFn: (allowDuplicate: boolean) =>
      submitAdmissionApplication(applicationId, { allowDuplicate }),
    onSuccess: async (updated) => {
      toast.success(`${fullName(updated)}'s application was submitted for review.`);
      setPendingDuplicate(false);
      await invalidate();
    },
    onError: async (error) => {
      if (error instanceof ApiRequestError && error.fieldErrors) {
        const duplicates =
          "duplicateApplicationId" in error.fieldErrors ||
          "duplicateStudentId" in error.fieldErrors;
        if (duplicates) {
          setPendingDuplicate(true);
          return;
        }
        setServerErrors(error.fieldErrors);
        setEditing(true);
        await invalidate();
        toast.error("Some details still need attention before this can be submitted.");
        return;
      }
      showError(error, "That submission failed. Please try again.");
    },
  });

  const startReview = useMutation({
    mutationFn: () => startAdmissionReview(applicationId),
    onSuccess: async () => {
      toast.success("Moved to review.");
      await invalidate();
    },
    onError: (error) => showError(error, "That action failed."),
  });

  const approve = useMutation({
    mutationFn: () =>
      approveAdmissionApplication(applicationId, {
        ...(admissionNumber.trim() ? { admissionNumber: admissionNumber.trim() } : {}),
      }),
    onSuccess: async (result) => {
      toast.success(`${fullName(result)} admitted as ${result.admissionNumber}.`, {
        description: result.access
          ? `Charged ${naira(result.access.amountKobo / 100)} for one month. Wallet balance: ${naira(result.access.walletBalanceKobo / 100)}.`
          : result.registrationFeeConfigured
            ? `Registration invoice of ${naira(Number(result.invoiceTotal) || 0)} raised.`
            : "Regular school fees are billed separately.",
        duration: 9000,
      });
      setApproving(false);
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: ["students"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 402) {
        setApproving(false);
        toast.error("Fund the wallet before admitting this student.", {
          description: error.message,
          action: { label: "Fund wallet", onClick: () => void navigate({ to: "/wallet" }) },
        });
        return;
      }
      showError(error, "We couldn't admit this applicant.");
    },
  });

  const reject = useMutation({
    mutationFn: () => rejectAdmissionApplication(applicationId, rejectReason),
    onSuccess: async () => {
      toast.success("Application rejected.");
      setRejecting(false);
      setRejectReason("");
      await invalidate();
    },
    onError: (error) => showError(error, "That rejection failed."),
  });

  const withdraw = useMutation({
    mutationFn: () => withdrawAdmissionApplication(applicationId),
    onSuccess: async () => {
      toast.success("Application withdrawn.");
      await invalidate();
    },
    onError: (error) => showError(error, "That withdrawal failed."),
  });

  if (application.isError) {
    return (
      <ErrorState
        message="We couldn't load this application. It may have been deleted."
        onRetry={() => void application.refetch()}
      />
    );
  }
  if (application.isPending || !application.data || !settings.data) {
    return <ListSkeleton />;
  }

  const app = application.data;
  const isDraft = app.status === "draft";
  const canReview = can("admissions.review");
  const canWrite = can("admissions.write");

  return (
    <PermissionGate permission="admissions.read">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <Button asChild variant="ghost" className="mb-2 h-10 pl-2">
            <Link to="/admissions">
              <ArrowLeft className="size-4" aria-hidden="true" />
              All applications
            </Link>
          </Button>
          <PageHeader
            title={fullName(app) || "New draft"}
            eyebrow={app.admissionNumber || `Applied for ${app.className || "—"}`}
            description={`${titleCase(app.applicantType)} applicant · ${
              app.submittedAt
                ? `submitted ${dateTimeFmt(app.submittedAt)}`
                : `draft saved ${dateTimeFmt(app.lastSavedAt)}`
            }`}
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={app.status} />
                {isDraft && canWrite ? (
                  <>
                    <Button
                      variant="outline"
                      className="h-11"
                      onClick={() => setEditing((value) => !value)}
                    >
                      <Pencil className="size-4" aria-hidden="true" />
                      {editing ? "Close editor" : "Edit details"}
                    </Button>
                    <Button
                      className="h-11"
                      disabled={submit.isPending}
                      onClick={() => submit.mutate(false)}
                    >
                      Submit for review
                    </Button>
                  </>
                ) : null}
                {canReview && app.status === "submitted" ? (
                  <Button
                    className="h-11"
                    variant="outline"
                    disabled={startReview.isPending}
                    onClick={() => startReview.mutate()}
                  >
                    Start review
                  </Button>
                ) : null}
                {canReview && (app.status === "submitted" || app.status === "under_review") ? (
                  <>
                    <Button className="h-11" onClick={() => setApproving(true)}>
                      <BadgeCheck className="size-4" aria-hidden="true" />
                      Admit student
                    </Button>
                    <Button
                      variant="ghost"
                      className="h-11 text-destructive"
                      onClick={() => setRejecting(true)}
                    >
                      <Ban className="size-4" aria-hidden="true" />
                      Reject
                    </Button>
                  </>
                ) : null}
                {canWrite && (app.status === "submitted" || app.status === "under_review") ? (
                  <ConfirmDialog
                    title="Withdraw this application?"
                    description="The application leaves the review queue and cannot be reviewed until it is resubmitted."
                    confirmLabel="Withdraw"
                    destructive
                    trigger={
                      <Button variant="ghost" className="h-11">
                        <Undo2 className="size-4" aria-hidden="true" />
                        Withdraw
                      </Button>
                    }
                    onConfirm={() => withdraw.mutate()}
                  />
                ) : null}
              </div>
            }
          />
        </div>

        {app.decisionReason ? (
          <div className="fn-panel p-4">
            <p className="text-sm font-medium">Decision note</p>
            <p className="text-sm text-muted-foreground">{app.decisionReason}</p>
            {app.reviewedBy ? (
              <p className="mt-1 text-sm text-muted-foreground">
                By {app.reviewedBy}
                {app.reviewedAt ? ` · ${dateTimeFmt(app.reviewedAt)}` : ""}
              </p>
            ) : null}
          </div>
        ) : null}

        {app.studentId ? (
          <div className="fn-panel flex flex-wrap items-center justify-between gap-3 p-4">
            <p className="text-sm text-muted-foreground">
              Admitted as <span className="font-medium text-foreground">{app.admissionNumber}</span>
            </p>
            <Button asChild variant="outline" className="h-11">
              <Link to="/students/$studentId" params={{ studentId: app.studentId }}>
                Open student record
              </Link>
            </Button>
          </div>
        ) : null}

        {isDraft && editing && canWrite ? (
          <AdmissionWizard
            settings={settings.data}
            defaultValues={toFormValues(app)}
            submitLabel="Save draft"
            isPending={save.isPending}
            serverErrors={serverErrors}
            onSubmit={(values) => save.mutate(values)}
            onCancel={
              <Button
                type="button"
                variant="outline"
                className="h-12"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
            }
          />
        ) : (
          <>
            <Section title="Applicant">
              <Info label="Class applied for" value={app.className || "—"} />
              <Info
                label="Date of birth"
                value={app.dateOfBirth ? dateFmt(app.dateOfBirth) : "—"}
              />
              <Info label="Gender" value={titleCase(app.gender || "—")} />
              <Info label="Nationality" value={app.nationality || "—"} />
              <Info
                label="State / LGA of origin"
                value={[app.stateOfOrigin, app.lgaOfOrigin].filter(Boolean).join(" / ") || "—"}
              />
              <Info label="Religion" value={app.religion || "—"} />
              <Info label="Academic session" value={app.academicSession || "—"} />
              <Info
                label="Admission year"
                value={app.admissionYear ? String(app.admissionYear) : "—"}
              />
            </Section>

            <Section title="Parent / guardian">
              <Info label="Name" value={app.guardianName || "—"} />
              <Info label="Relationship" value={app.guardianRelationship || "—"} />
              <Info label="Phone" value={app.guardianPhone || "—"} />
              <Info label="Email" value={app.guardianEmail || "—"} />
              <Info label="Occupation" value={app.guardianOccupation || "—"} />
              <Info label="Address" value={app.guardianAddress || "—"} />
              <Info
                label="Second guardian"
                value={
                  [app.secondGuardianName, app.secondGuardianPhone].filter(Boolean).join(" · ") ||
                  "—"
                }
              />
            </Section>

            <Section title="Health & emergency">
              <Info label="Blood group" value={app.bloodGroup || "—"} />
              <Info label="Allergies" value={app.allergies || "—"} />
              <Info label="Medical conditions" value={app.medicalConditions || "—"} />
              <Info
                label="Emergency contact"
                value={
                  [app.emergencyContactName, app.emergencyContactPhone]
                    .filter(Boolean)
                    .join(" · ") || "—"
                }
              />
            </Section>

            {app.applicantType === "transfer" ? (
              <Section title="Previous school">
                <Info label="School" value={app.previousSchoolName || "—"} />
                <Info label="Last class completed" value={app.lastClassCompleted || "—"} />
                <Info label="Address" value={app.previousSchoolAddress || "—"} />
                <Info label="Reason for transfer" value={app.reasonForTransfer || "—"} />
              </Section>
            ) : null}

            {app.refereeName || app.sponsorName ? (
              <Section title="Referee & sponsor">
                <Info
                  label="Referee"
                  value={[app.refereeName, app.refereePhone].filter(Boolean).join(" · ") || "—"}
                />
                <Info
                  label="Sponsor"
                  value={
                    [app.sponsorName, app.sponsorRelationship, app.sponsorPhone]
                      .filter(Boolean)
                      .join(" · ") || "—"
                  }
                />
              </Section>
            ) : null}

            <Section title="Declaration">
              <Info label="Declared by" value={app.declaredBy || "—"} />
              <Info
                label="Declared at"
                value={app.declaredAt ? dateTimeFmt(app.declaredAt) : "Not signed"}
              />
              <Info label="Mailing address" value={app.mailingAddress || "—"} />
            </Section>
          </>
        )}

        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <ShieldCheck className="size-5 text-brass" aria-hidden="true" />
            Documents
          </h2>
          <DocumentPanel
            applicationId={applicationId}
            documents={app.documents ?? []}
            requiredDocuments={settings.data.requiredDocuments}
            editable={app.status !== "approved" && app.status !== "rejected" && app.status !== "withdrawn"}
            canWrite={canWrite}
            canReview={canReview}
          />
        </section>
      </div>

      <Dialog open={approving} onOpenChange={setApproving}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Admit {fullName(app) || "this applicant"}</DialogTitle>
            <DialogDescription>
              This creates the student record, raises the registration invoice and activates access
              from the school wallet. Required documents must already be verified.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="admissionNumber">Admission number (optional)</Label>
            <Input
              id="admissionNumber"
              className="h-12"
              placeholder="Leave blank to generate one"
              value={admissionNumber}
              onChange={(event) => setAdmissionNumber(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproving(false)}>
              Cancel
            </Button>
            <Button disabled={approve.isPending} onClick={() => approve.mutate()}>
              {approve.isPending ? "Admitting…" : "Admit student"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejecting} onOpenChange={setRejecting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this application?</DialogTitle>
            <DialogDescription>
              The family can be told why. This is kept on the record.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="rejectReason">Reason</Label>
            <Textarea
              id="rejectReason"
              rows={3}
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={reject.isPending || rejectReason.trim() === ""}
              onClick={() => reject.mutate()}
            >
              Reject application
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingDuplicate}
        onOpenChange={(open) => !open && setPendingDuplicate(false)}
        title="A similar application already exists"
        description="A child with the same name and date of birth is already recorded. If this is genuinely a different child, you can submit anyway."
        confirmLabel="Submit anyway"
        onConfirm={() => submit.mutate(true)}
      />
    </PermissionGate>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="fn-panel space-y-3 p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <dl className="grid gap-3 sm:grid-cols-2">{children}</dl>
    </section>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value}</dd>
    </div>
  );
}
