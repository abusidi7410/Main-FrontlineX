import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { ARMS } from "@/constants/reference";
import { ApiRequestError } from "@/api/client";
import { createStudent } from "@/services/students.service";
import { StudentForm } from "@/features/students/student-form";
import { naira, dateFmt } from "@/lib/format";
import { invalidateEnrollmentQueries } from "@/lib/query-invalidation";

/**
 * Turn DRF's `{ fieldErrors: {...} }` body into one readable sentence, so a
 * validation failure tells the user what to fix instead of a generic apology.
 */
function describeFieldErrors(error: ApiRequestError): string {
  const fieldErrors = error.fieldErrors;
  if (fieldErrors && Object.keys(fieldErrors).length > 0) {
    const messages = Object.values(fieldErrors)
      .flatMap((value) => (Array.isArray(value) ? value : [value]))
      .filter((value): value is string => typeof value === "string");
    if (messages.length === 1 && messages[0] !== undefined) {
      return messages[0];
    }
    if (messages.length > 1) {
      return messages.join(" ");
    }
  }
  return error.message;
}

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
  const [fundingBlocked, setFundingBlocked] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: createStudent,
    onSuccess: async ({ student, invoiceTotal, registrationFeeConfigured, access }) => {
      toast.success(`${student.firstName} ${student.lastName} activated successfully.`, {
        description: access
          ? `Charged ${naira(access.amountKobo / 100)} for one month. Access expires on ${dateFmt(access.periodEnd)}. Wallet balance: ${naira(access.walletBalanceKobo / 100)}.${registrationFeeConfigured ? ` Registration invoice of ${naira(Number(invoiceTotal) || 0)} also raised.` : ""}`
          : registrationFeeConfigured
            ? `One-time registration invoice of ${naira(Number(invoiceTotal) || 0)} raised. Regular school fees are billed separately.`
            : "No registration fee applies, so the student is active. Regular school fees can be billed separately.",
        duration: 9000,
      });
      await invalidateEnrollmentQueries(queryClient, [["invoices"]]);
      void navigate({ to: "/students" });
    },
    onError: (error) => {
      // A 402 means the wallet cannot cover even one activation: block with
      // the funding message instead of a generic failure.
      if (error instanceof ApiRequestError && error.status === 402) {
        setFundingBlocked(error.message);
        toast.error("Fund your wallet before adding students.");
        return;
      }
      // Surface the real reason. A duplicate admission number or a missing
      // guardian field is a specific, fixable problem - a generic message
      // made the form look broken with no indication of what to change.
      toast.error(
        error instanceof ApiRequestError
          ? describeFieldErrors(error)
          : "We couldn't save this student. Please check the details and try again.",
      );
    },
  });

  return (
    <PermissionGate permission="students.write">
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader
          title="Add a student"
          description="Only the essentials now — you can complete the full profile later."
        />

        {fundingBlocked ? (
          <div
            role="alert"
            className="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
          >
            <p className="font-medium">Student was not created.</p>
            <p className="mt-1 text-muted-foreground">{fundingBlocked}</p>
            <Link to="/wallet" className="mt-2 inline-block font-medium underline">
              Fund wallet
            </Link>
          </div>
        ) : null}

        <StudentForm
          defaultValues={{
            firstName: "",
            lastName: "",
            admissionNumber: "",
            gender: "male",
            dateOfBirth: "",
            className: "",
            arm: ARMS[0] ?? "",
            guardianName: "",
            guardianPhone: "",
          }}
          submitLabel="Save student"
          isPending={mutation.isPending}
          onSubmit={(values) => {
            setFundingBlocked(null);
            // Drop the key entirely when blank so the server generates the
            // number instead of receiving an empty string.
            mutation.mutate(
              values.admissionNumber
                ? values
                : (({ admissionNumber: _omitted, ...rest }) => rest)(values),
            );
          }}
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
