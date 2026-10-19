import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/api/client";
import { updateAdmissionSettings } from "@/services/admissions.service";
import { useAdmissionSettings } from "@/features/admissions/admission-wizard";
import {
  ADMISSION_DOCUMENT_CATEGORIES,
  ADMISSION_DOCUMENT_LABELS,
  type AdmissionDocumentCategory,
  type AdmissionSettings,
} from "@/types";

export const Route = createFileRoute("/_app/admissions/settings")({
  head: () => ({
    meta: [
      { title: "Admission requirements — Frontline Nexus" },
      {
        name: "description",
        content: "Choose which documents and declarations your school requires from applicants.",
      },
      { property: "og:title", content: "Admission requirements — Frontline Nexus" },
      {
        property: "og:description",
        content: "Choose which documents and declarations your school requires from applicants.",
      },
      { property: "robots", content: "noindex" },
    ],
  }),
  component: AdmissionSettingsPage,
});

function AdmissionSettingsPage() {
  const settings = useAdmissionSettings();

  return (
    <PermissionGate permission="admissions.settings">
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader
          title="Admission requirements"
          description="These rules apply to every new application. Approval is blocked until each required document has been verified."
        />
        {settings.isError ? (
          <ErrorState
            message="We couldn't load your admission requirements."
            onRetry={() => void settings.refetch()}
          />
        ) : settings.isPending || !settings.data ? (
          <ListSkeleton rows={4} />
        ) : (
          <SettingsForm key={settings.dataUpdatedAt} settings={settings.data} />
        )}
      </div>
    </PermissionGate>
  );
}

type FormState = AdmissionSettings;

function SettingsForm({ settings }: { settings: AdmissionSettings }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>({
    requiredDocuments: settings.requiredDocuments,
    refereeRequired: settings.refereeRequired,
    sponsorEnabled: settings.sponsorEnabled,
    requirePreviousSchoolForTransfer: settings.requirePreviousSchoolForTransfer,
    declarationText: settings.declarationText,
  });
  const [declarationError, setDeclarationError] = useState("");

  useEffect(() => {
    setForm({
      requiredDocuments: settings.requiredDocuments,
      refereeRequired: settings.refereeRequired,
      sponsorEnabled: settings.sponsorEnabled,
      requirePreviousSchoolForTransfer: settings.requirePreviousSchoolForTransfer,
      declarationText: settings.declarationText,
    });
  }, [settings]);

  const save = useMutation({
    mutationFn: (input: Partial<AdmissionSettings>) => updateAdmissionSettings(input),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["admission-settings"], updated);
      await queryClient.invalidateQueries({ queryKey: ["admission-settings"] });
      toast.success("Admission requirements saved.");
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "We couldn't save these requirements. Please try again.",
      );
    },
  });

  const toggleDocument = (category: AdmissionDocumentCategory, checked: boolean) => {
    setForm((current) => ({
      ...current,
      requiredDocuments: checked
        ? [...current.requiredDocuments, category]
        : current.requiredDocuments.filter((item) => item !== category),
    }));
  };

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (form.declarationText.trim().length < 10) {
          setDeclarationError("Write a short declaration for the family to accept.");
          return;
        }
        setDeclarationError("");
        save.mutate({ ...form, declarationText: form.declarationText.trim() });
      }}
    >
      <section className="fn-panel space-y-4 p-5">
        <div>
          <h2 className="text-lg font-semibold">Required documents</h2>
          <p className="text-sm text-muted-foreground">
            Applicants can still submit without them, but the application cannot be approved until
            each one is uploaded and verified.
          </p>
        </div>
        <ul className="grid gap-3 sm:grid-cols-2">
          {ADMISSION_DOCUMENT_CATEGORIES.map((category) => {
            const checked = form.requiredDocuments.includes(category);
            const id = `required-${category}`;
            return (
              <li key={category} className="flex items-center gap-3 rounded-xl border p-3">
                <Checkbox
                  id={id}
                  checked={checked}
                  onCheckedChange={(value) => toggleDocument(category, value === true)}
                />
                <Label htmlFor={id} className="cursor-pointer font-normal">
                  {ADMISSION_DOCUMENT_LABELS[category]}
                </Label>
              </li>
            );
          })}
        </ul>
        <p className="text-sm text-muted-foreground">
          {form.requiredDocuments.length === 0
            ? "No documents required — applications can be approved immediately."
            : `${form.requiredDocuments.length} document type${
                form.requiredDocuments.length === 1 ? "" : "s"
              } required.`}
        </p>
      </section>

      <section className="fn-panel space-y-4 p-5">
        <h2 className="text-lg font-semibold">Application rules</h2>
        <ToggleRow
          id="refereeRequired"
          label="Require a referee"
          description="The applicant must name a referee before submitting."
          checked={form.refereeRequired}
          onChange={(checked) => setForm((current) => ({ ...current, refereeRequired: checked }))}
        />
        <ToggleRow
          id="sponsorEnabled"
          label="Collect sponsor details"
          description="Show an optional sponsor section on the application."
          checked={form.sponsorEnabled}
          onChange={(checked) => setForm((current) => ({ ...current, sponsorEnabled: checked }))}
        />
        <ToggleRow
          id="requirePreviousSchoolForTransfer"
          label="Previous school for transfers"
          description="A transfer applicant must name the previous school and last class completed."
          checked={form.requirePreviousSchoolForTransfer}
          onChange={(checked) =>
            setForm((current) => ({ ...current, requirePreviousSchoolForTransfer: checked }))
          }
        />
      </section>

      <section className="fn-panel space-y-3 p-5">
        <h2 className="text-lg font-semibold">Declaration</h2>
        <p className="text-sm text-muted-foreground">
          Shown to the family at the end of the application. They type their name to accept it.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="declarationText">Declaration text</Label>
          <Textarea
            id="declarationText"
            rows={5}
            value={form.declarationText}
            onChange={(event) => {
              setForm((current) => ({ ...current, declarationText: event.target.value }));
              setDeclarationError("");
            }}
          />
          {declarationError ? (
            <p role="alert" className="text-sm text-destructive">
              {declarationError}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Keep it short, plain and specific to your school.
            </p>
          )}
        </div>
      </section>

      <div className="flex justify-end">
        <Button type="submit" className="h-12 text-base" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save requirements"}
        </Button>
      </div>
    </form>
  );
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-t pt-4 first:border-t-0 first:pt-0">
      <div className="space-y-0.5">
        <Label htmlFor={id} className="cursor-pointer">
          {label}
        </Label>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
