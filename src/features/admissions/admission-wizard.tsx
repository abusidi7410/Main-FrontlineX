import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthenticatedSession } from "@/auth/session";
import { getAcademicStructure } from "@/services/academics.service";
import { getAdmissionSettings } from "@/services/admissions.service";
import { ngPhone, normalizeNigerianPhone } from "@/lib/validation";
import type { AdmissionApplication, AdmissionApplicationInput, AdmissionSettings } from "@/types";

export interface AdmissionFormValues {
  applicantType: "new" | "transfer" | "returning";
  firstName: string;
  middleName: string;
  lastName: string;
  gender: "male" | "female";
  dateOfBirth: string;
  nationality: string;
  stateOfOrigin: string;
  lgaOfOrigin: string;
  religion: string;
  className: string;
  admissionYear: string;
  guardianName: string;
  guardianRelationship: string;
  guardianPhone: string;
  guardianEmail: string;
  guardianOccupation: string;
  guardianAddress: string;
  secondGuardianName: string;
  secondGuardianPhone: string;
  bloodGroup: string;
  allergies: string;
  medicalConditions: string;
  emergencyContactName: string;
  emergencyContactPhone: string;
  previousSchoolName: string;
  previousSchoolAddress: string;
  lastClassCompleted: string;
  reasonForTransfer: string;
  refereeName: string;
  refereePhone: string;
  refereeAddress: string;
  sponsorName: string;
  sponsorRelationship: string;
  sponsorPhone: string;
  sponsorEmail: string;
  sponsorAddress: string;
  mailingAddress: string;
  declaredBy: string;
}

export const EMPTY_ADMISSION: AdmissionFormValues = {
  applicantType: "new",
  firstName: "",
  middleName: "",
  lastName: "",
  gender: "male",
  dateOfBirth: "",
  nationality: "Nigerian",
  stateOfOrigin: "",
  lgaOfOrigin: "",
  religion: "",
  className: "",
  admissionYear: "",
  guardianName: "",
  guardianRelationship: "",
  guardianPhone: "",
  guardianEmail: "",
  guardianOccupation: "",
  guardianAddress: "",
  secondGuardianName: "",
  secondGuardianPhone: "",
  bloodGroup: "",
  allergies: "",
  medicalConditions: "",
  emergencyContactName: "",
  emergencyContactPhone: "",
  previousSchoolName: "",
  previousSchoolAddress: "",
  lastClassCompleted: "",
  reasonForTransfer: "",
  refereeName: "",
  refereePhone: "",
  refereeAddress: "",
  sponsorName: "",
  sponsorRelationship: "",
  sponsorPhone: "",
  sponsorEmail: "",
  sponsorAddress: "",
  mailingAddress: "",
  declaredBy: "",
};

const optionalText = z.string().trim().max(255).optional().default("");

function buildSchema(settings: AdmissionSettings) {
  return z
    .object({
      applicantType: z.enum(["new", "transfer", "returning"]),
      firstName: z.string().trim().min(1, { message: "First name is required" }).max(150),
      middleName: optionalText,
      lastName: z.string().trim().min(1, { message: "Surname is required" }).max(150),
      gender: z.enum(["male", "female"]),
      dateOfBirth: z.string().trim().min(1, { message: "Date of birth is required" }),
      nationality: z.string().trim().min(1, { message: "Nationality is required" }).max(100),
      stateOfOrigin: optionalText,
      lgaOfOrigin: optionalText,
      religion: optionalText,
      className: z.string().trim().min(1, { message: "Class applied for is required" }),
      admissionYear: z.string().trim().optional().default(""),
      guardianName: z
        .string()
        .trim()
        .min(1, { message: "Parent / guardian name is required" })
        .max(200),
      guardianRelationship: optionalText,
      guardianPhone: ngPhone,
      guardianEmail: z
        .string()
        .trim()
        .max(254)
        .optional()
        .default("")
        .refine((v) => v === "" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v), {
          message: "Enter a valid email address",
        }),
      guardianOccupation: optionalText,
      guardianAddress: z.string().trim().min(1, { message: "Home address is required" }),
      secondGuardianName: optionalText,
      secondGuardianPhone: optionalText,
      bloodGroup: optionalText,
      allergies: optionalText,
      medicalConditions: z.string().trim().max(2000).optional().default(""),
      emergencyContactName: optionalText,
      emergencyContactPhone: optionalText,
      previousSchoolName: optionalText,
      previousSchoolAddress: z.string().trim().max(2000).optional().default(""),
      lastClassCompleted: optionalText,
      reasonForTransfer: z.string().trim().max(2000).optional().default(""),
      refereeName: optionalText,
      refereePhone: optionalText,
      refereeAddress: z.string().trim().max(2000).optional().default(""),
      sponsorName: optionalText,
      sponsorRelationship: optionalText,
      sponsorPhone: optionalText,
      sponsorEmail: z
        .string()
        .trim()
        .max(254)
        .optional()
        .default("")
        .refine((v) => v === "" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v), {
          message: "Enter a valid email address",
        }),
      sponsorAddress: z.string().trim().max(2000).optional().default(""),
      mailingAddress: z.string().trim().max(2000).optional().default(""),
      declaredBy: z
        .string()
        .trim()
        .min(1, { message: "Type the guardian's name to sign the declaration" })
        .max(200),
    })
    .superRefine((values, ctx) => {
      if (settings.requirePreviousSchoolForTransfer && values.applicantType === "transfer") {
        if (values.previousSchoolName.trim() === "") {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["previousSchoolName"],
            message: "The previous school is required for a transfer applicant",
          });
        }
      }
      if (settings.refereeRequired && values.refereeName.trim() === "") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["refereeName"],
          message: "A referee is required for this school",
        });
      }
    });
}

const STEP_FIELDS: (keyof AdmissionFormValues)[][] = [
  [
    "applicantType",
    "firstName",
    "middleName",
    "lastName",
    "gender",
    "dateOfBirth",
    "nationality",
    "stateOfOrigin",
    "lgaOfOrigin",
    "religion",
    "className",
    "admissionYear",
  ],
  [
    "guardianName",
    "guardianRelationship",
    "guardianPhone",
    "guardianEmail",
    "guardianOccupation",
    "guardianAddress",
    "secondGuardianName",
    "secondGuardianPhone",
  ],
  ["bloodGroup", "allergies", "medicalConditions", "emergencyContactName", "emergencyContactPhone"],
  [
    "previousSchoolName",
    "previousSchoolAddress",
    "lastClassCompleted",
    "reasonForTransfer",
    "refereeName",
    "refereePhone",
    "refereeAddress",
    "sponsorName",
    "sponsorRelationship",
    "sponsorPhone",
    "sponsorEmail",
    "sponsorAddress",
    "mailingAddress",
    "declaredBy",
  ],
];

const STEP_LABELS = ["Applicant", "Guardian", "Health & emergency", "History & declaration"];

/** Map a saved application back into form values (used by the edit screen). */
export function toFormValues(application: AdmissionApplication): AdmissionFormValues {
  return {
    ...EMPTY_ADMISSION,
    applicantType: application.applicantType,
    firstName: application.firstName,
    middleName: application.middleName,
    lastName: application.lastName,
    gender: application.gender === "female" ? "female" : "male",
    dateOfBirth: application.dateOfBirth ?? "",
    nationality: application.nationality || "Nigerian",
    stateOfOrigin: application.stateOfOrigin,
    lgaOfOrigin: application.lgaOfOrigin,
    religion: application.religion,
    className: application.className,
    admissionYear: application.admissionYear ? String(application.admissionYear) : "",
    guardianName: application.guardianName,
    guardianRelationship: application.guardianRelationship,
    guardianPhone: application.guardianPhone,
    guardianEmail: application.guardianEmail,
    guardianOccupation: application.guardianOccupation,
    guardianAddress: application.guardianAddress,
    secondGuardianName: application.secondGuardianName,
    secondGuardianPhone: application.secondGuardianPhone,
    bloodGroup: application.bloodGroup,
    allergies: application.allergies,
    medicalConditions: application.medicalConditions,
    emergencyContactName: application.emergencyContactName,
    emergencyContactPhone: application.emergencyContactPhone,
    previousSchoolName: application.previousSchoolName,
    previousSchoolAddress: application.previousSchoolAddress,
    lastClassCompleted: application.lastClassCompleted,
    reasonForTransfer: application.reasonForTransfer,
    refereeName: application.refereeName,
    refereePhone: application.refereePhone,
    refereeAddress: application.refereeAddress,
    sponsorName: application.sponsorName,
    sponsorRelationship: application.sponsorRelationship,
    sponsorPhone: application.sponsorPhone,
    sponsorEmail: application.sponsorEmail,
    sponsorAddress: application.sponsorAddress,
    mailingAddress: application.mailingAddress,
    declaredBy: application.declaredBy,
  };
}

/**
 * Turn wizard values into the API payload. The class is a name in the UI (that
 * is what a school recognises) and an id on the wire, so the caller passes the
 * class id map it already loaded.
 */
export function toAdmissionInput(
  values: AdmissionFormValues,
  classIds: Record<string, number>,
  sessionId: number | null,
): AdmissionApplicationInput {
  const year = Number(values.admissionYear);
  return {
    applicantType: values.applicantType,
    firstName: values.firstName,
    middleName: values.middleName,
    lastName: values.lastName,
    gender: values.gender,
    dateOfBirth: values.dateOfBirth || null,
    nationality: values.nationality,
    stateOfOrigin: values.stateOfOrigin,
    lgaOfOrigin: values.lgaOfOrigin,
    religion: values.religion,
    classId: classIds[values.className] ?? null,
    academicSessionId: sessionId,
    admissionYear: Number.isFinite(year) && year >= 1900 && year <= 2100 ? year : null,
    guardianName: values.guardianName,
    guardianRelationship: values.guardianRelationship,
    guardianPhone: normalizeNigerianPhone(values.guardianPhone) ?? values.guardianPhone,
    guardianEmail: values.guardianEmail,
    guardianOccupation: values.guardianOccupation,
    guardianAddress: values.guardianAddress,
    secondGuardianName: values.secondGuardianName,
    secondGuardianPhone: values.secondGuardianPhone,
    bloodGroup: values.bloodGroup,
    allergies: values.allergies,
    medicalConditions: values.medicalConditions,
    emergencyContactName: values.emergencyContactName,
    emergencyContactPhone: values.emergencyContactPhone,
    previousSchoolName: values.previousSchoolName,
    previousSchoolAddress: values.previousSchoolAddress,
    lastClassCompleted: values.lastClassCompleted,
    reasonForTransfer: values.reasonForTransfer,
    refereeName: values.refereeName,
    refereePhone: values.refereePhone,
    refereeAddress: values.refereeAddress,
    sponsorName: values.sponsorName,
    sponsorRelationship: values.sponsorRelationship,
    sponsorPhone: values.sponsorPhone,
    sponsorEmail: values.sponsorEmail,
    sponsorAddress: values.sponsorAddress,
    mailingAddress: values.mailingAddress,
    declaredBy: values.declaredBy,
  };
}

export function AdmissionWizard({
  settings,
  defaultValues,
  submitLabel,
  isPending,
  onSubmit,
  onCancel,
  serverErrors,
}: {
  settings: AdmissionSettings;
  defaultValues: AdmissionFormValues;
  submitLabel: string;
  isPending: boolean;
  onSubmit: (values: AdmissionFormValues) => void;
  onCancel: ReactNode;
  serverErrors?: Record<string, string> | undefined;
}) {
  const { school } = useAuthenticatedSession();
  const [step, setStep] = useState(0);
  const schema = useMemo(() => buildSchema(settings), [settings]);
  const form = useForm<AdmissionFormValues>({
    // The schema's input type allows empty optional fields, while the form type
    // is the schema's output (defaults applied), so the two are bridged here.
    resolver: zodResolver(schema) as unknown as Resolver<AdmissionFormValues>,
    defaultValues,
    mode: "onTouched",
  });

  const academics = useQuery({
    queryKey: ["academics"],
    queryFn: getAcademicStructure,
  });
  const classes = useMemo(() => academics.data?.classes ?? [], [academics.data?.classes]);
  const availableClasses = useMemo(
    () => [...new Set([...classes, defaultValues.className].filter(Boolean))],
    [classes, defaultValues.className],
  );

  useEffect(() => {
    if (!form.getValues("className") && classes[0]) {
      form.setValue("className", classes[0], { shouldValidate: false });
    }
  }, [classes, form]);

  useEffect(() => {
    if (!serverErrors) return;
    for (const [field, message] of Object.entries(serverErrors)) {
      if (field in EMPTY_ADMISSION) {
        form.setError(field as keyof AdmissionFormValues, { message });
      }
    }
  }, [serverErrors, form]);

  if (academics.isError) {
    return (
      <ErrorState
        message="School classes could not be loaded, so we can't safely take an application."
        onRetry={() => void academics.refetch()}
      />
    );
  }
  if (academics.isPending) return <CardsSkeleton count={2} />;

  const isLastStep = step === STEP_FIELDS.length - 1;
  const next = async () => {
    const fields = STEP_FIELDS[step] ?? [];
    const valid = await form.trigger(fields);
    if (valid) setStep((current) => Math.min(current + 1, STEP_FIELDS.length - 1));
  };

  const guardian = form.watch("guardianName") || form.watch("firstName");

  return (
    <form noValidate className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
      <ol className="fn-panel flex flex-wrap gap-2 p-3" aria-label="Application steps">
        {STEP_LABELS.map((label, index) => (
          <li key={label} className="flex-1">
            <button
              type="button"
              onClick={() => {
                // Only move backwards freely; forward needs the current step to pass.
                if (index < step) setStep(index);
                else if (index === step) return;
                else void next();
              }}
              aria-current={index === step ? "step" : undefined}
              className={`w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                index === step
                  ? "bg-brass/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <span className="block text-xs uppercase tracking-wide">Step {index + 1}</span>
              <span className="font-medium">{label}</span>
            </button>
          </li>
        ))}
      </ol>

      <div className="fn-panel space-y-4 p-5">
        {step === 0 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Applicant type"
              id="applicantType"
              error={form.formState.errors.applicantType?.message}
            >
              <Select
                value={form.watch("applicantType")}
                onValueChange={(value) =>
                  form.setValue("applicantType", value as AdmissionFormValues["applicantType"])
                }
              >
                <SelectTrigger id="applicantType" className="h-12">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">New applicant</SelectItem>
                  <SelectItem value="transfer">Transfer applicant</SelectItem>
                  <SelectItem value="returning">Returning student</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Class applied for"
              id="className"
              error={form.formState.errors.className?.message}
            >
              <Select
                value={form.watch("className")}
                onValueChange={(value) =>
                  form.setValue("className", value, { shouldValidate: true })
                }
              >
                <SelectTrigger
                  id="className"
                  className="h-12"
                  disabled={availableClasses.length === 0}
                >
                  <SelectValue placeholder="Select a class" />
                </SelectTrigger>
                <SelectContent>
                  {availableClasses.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {classes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Set up a class before taking applications.
                </p>
              ) : null}
            </Field>
            <Field
              label="First name"
              id="firstName"
              error={form.formState.errors.firstName?.message}
            >
              <Input id="firstName" className="h-12" {...form.register("firstName")} />
            </Field>
            <Field
              label="Middle name"
              id="middleName"
              optional
              error={form.formState.errors.middleName?.message}
            >
              <Input id="middleName" className="h-12" {...form.register("middleName")} />
            </Field>
            <Field label="Surname" id="lastName" error={form.formState.errors.lastName?.message}>
              <Input id="lastName" className="h-12" {...form.register("lastName")} />
            </Field>
            <Field label="Gender" id="gender" error={form.formState.errors.gender?.message}>
              <Select
                value={form.watch("gender")}
                onValueChange={(value) => form.setValue("gender", value as "male" | "female")}
              >
                <SelectTrigger id="gender" className="h-12">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Date of birth"
              id="dateOfBirth"
              error={form.formState.errors.dateOfBirth?.message}
            >
              <Input
                id="dateOfBirth"
                type="date"
                className="h-12"
                {...form.register("dateOfBirth")}
              />
            </Field>
            <Field
              label="Nationality"
              id="nationality"
              error={form.formState.errors.nationality?.message}
            >
              <Input id="nationality" className="h-12" {...form.register("nationality")} />
            </Field>
            <Field
              label="State of origin"
              id="stateOfOrigin"
              optional
              error={form.formState.errors.stateOfOrigin?.message}
            >
              <Input id="stateOfOrigin" className="h-12" {...form.register("stateOfOrigin")} />
            </Field>
            <Field
              label="LGA of origin"
              id="lgaOfOrigin"
              optional
              error={form.formState.errors.lgaOfOrigin?.message}
            >
              <Input id="lgaOfOrigin" className="h-12" {...form.register("lgaOfOrigin")} />
            </Field>
            <Field
              label="Religion"
              id="religion"
              optional
              error={form.formState.errors.religion?.message}
            >
              <Input id="religion" className="h-12" {...form.register("religion")} />
            </Field>
            <Field
              label="Admission year"
              id="admissionYear"
              optional
              hint={
                school?.currentSession ? `Current session: ${school.currentSession}` : undefined
              }
              error={form.formState.errors.admissionYear?.message}
            >
              <Input
                id="admissionYear"
                inputMode="numeric"
                placeholder="e.g. 2026"
                className="h-12"
                {...form.register("admissionYear")}
              />
            </Field>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Parent / guardian name"
              id="guardianName"
              error={form.formState.errors.guardianName?.message}
            >
              <Input id="guardianName" className="h-12" {...form.register("guardianName")} />
            </Field>
            <Field
              label="Relationship"
              id="guardianRelationship"
              optional
              error={form.formState.errors.guardianRelationship?.message}
            >
              <Input
                id="guardianRelationship"
                className="h-12"
                placeholder="e.g. Father"
                {...form.register("guardianRelationship")}
              />
            </Field>
            <Field
              label="Phone"
              id="guardianPhone"
              error={form.formState.errors.guardianPhone?.message}
            >
              <Input
                id="guardianPhone"
                inputMode="tel"
                placeholder="08012345678"
                className="h-12"
                {...form.register("guardianPhone")}
              />
            </Field>
            <Field
              label="Email"
              id="guardianEmail"
              optional
              error={form.formState.errors.guardianEmail?.message}
            >
              <Input
                id="guardianEmail"
                type="email"
                className="h-12"
                {...form.register("guardianEmail")}
              />
            </Field>
            <Field
              label="Occupation"
              id="guardianOccupation"
              optional
              error={form.formState.errors.guardianOccupation?.message}
            >
              <Input
                id="guardianOccupation"
                className="h-12"
                {...form.register("guardianOccupation")}
              />
            </Field>
            <Field
              label="Address"
              id="guardianAddress"
              error={form.formState.errors.guardianAddress?.message}
            >
              <Input id="guardianAddress" className="h-12" {...form.register("guardianAddress")} />
            </Field>
            <Field
              label="Second guardian"
              id="secondGuardianName"
              optional
              error={form.formState.errors.secondGuardianName?.message}
            >
              <Input
                id="secondGuardianName"
                className="h-12"
                {...form.register("secondGuardianName")}
              />
            </Field>
            <Field
              label="Second guardian phone"
              id="secondGuardianPhone"
              optional
              error={form.formState.errors.secondGuardianPhone?.message}
            >
              <Input
                id="secondGuardianPhone"
                inputMode="tel"
                className="h-12"
                {...form.register("secondGuardianPhone")}
              />
            </Field>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Blood group"
              id="bloodGroup"
              optional
              error={form.formState.errors.bloodGroup?.message}
            >
              <Input id="bloodGroup" className="h-12" {...form.register("bloodGroup")} />
            </Field>
            <Field
              label="Allergies"
              id="allergies"
              optional
              error={form.formState.errors.allergies?.message}
            >
              <Input id="allergies" className="h-12" {...form.register("allergies")} />
            </Field>
            <Field
              label="Medical conditions"
              id="medicalConditions"
              optional
              error={form.formState.errors.medicalConditions?.message}
            >
              <Textarea id="medicalConditions" rows={3} {...form.register("medicalConditions")} />
            </Field>
            <div className="hidden sm:block" aria-hidden="true" />
            <Field
              label="Emergency contact"
              id="emergencyContactName"
              optional
              error={form.formState.errors.emergencyContactName?.message}
            >
              <Input
                id="emergencyContactName"
                className="h-12"
                {...form.register("emergencyContactName")}
              />
            </Field>
            <Field
              label="Emergency contact phone"
              id="emergencyContactPhone"
              optional
              error={form.formState.errors.emergencyContactPhone?.message}
            >
              <Input
                id="emergencyContactPhone"
                inputMode="tel"
                className="h-12"
                {...form.register("emergencyContactPhone")}
              />
            </Field>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Previous school"
              id="previousSchoolName"
              optional={!settings.requirePreviousSchoolForTransfer}
              error={form.formState.errors.previousSchoolName?.message}
            >
              <Input
                id="previousSchoolName"
                className="h-12"
                {...form.register("previousSchoolName")}
              />
            </Field>
            <Field
              label="Last class completed"
              id="lastClassCompleted"
              optional
              error={form.formState.errors.lastClassCompleted?.message}
            >
              <Input
                id="lastClassCompleted"
                className="h-12"
                {...form.register("lastClassCompleted")}
              />
            </Field>
            <Field
              label="Previous school address"
              id="previousSchoolAddress"
              optional
              error={form.formState.errors.previousSchoolAddress?.message}
            >
              <Textarea
                id="previousSchoolAddress"
                rows={2}
                {...form.register("previousSchoolAddress")}
              />
            </Field>
            <Field
              label="Reason for transfer"
              id="reasonForTransfer"
              optional
              error={form.formState.errors.reasonForTransfer?.message}
            >
              <Textarea id="reasonForTransfer" rows={2} {...form.register("reasonForTransfer")} />
            </Field>
            <Field
              label="Referee"
              id="refereeName"
              optional={!settings.refereeRequired}
              error={form.formState.errors.refereeName?.message}
            >
              <Input id="refereeName" className="h-12" {...form.register("refereeName")} />
            </Field>
            <Field
              label="Referee phone"
              id="refereePhone"
              optional
              error={form.formState.errors.refereePhone?.message}
            >
              <Input
                id="refereePhone"
                inputMode="tel"
                className="h-12"
                {...form.register("refereePhone")}
              />
            </Field>
            <Field
              label="Referee address"
              id="refereeAddress"
              optional
              error={form.formState.errors.refereeAddress?.message}
            >
              <Textarea id="refereeAddress" rows={2} {...form.register("refereeAddress")} />
            </Field>
            {settings.sponsorEnabled ? (
              <>
                <Field
                  label="Sponsor"
                  id="sponsorName"
                  optional
                  error={form.formState.errors.sponsorName?.message}
                >
                  <Input id="sponsorName" className="h-12" {...form.register("sponsorName")} />
                </Field>
                <Field
                  label="Sponsor relationship"
                  id="sponsorRelationship"
                  optional
                  error={form.formState.errors.sponsorRelationship?.message}
                >
                  <Input
                    id="sponsorRelationship"
                    className="h-12"
                    {...form.register("sponsorRelationship")}
                  />
                </Field>
                <Field
                  label="Sponsor phone"
                  id="sponsorPhone"
                  optional
                  error={form.formState.errors.sponsorPhone?.message}
                >
                  <Input
                    id="sponsorPhone"
                    inputMode="tel"
                    className="h-12"
                    {...form.register("sponsorPhone")}
                  />
                </Field>
                <Field
                  label="Sponsor email"
                  id="sponsorEmail"
                  optional
                  error={form.formState.errors.sponsorEmail?.message}
                >
                  <Input
                    id="sponsorEmail"
                    type="email"
                    className="h-12"
                    {...form.register("sponsorEmail")}
                  />
                </Field>
                <Field
                  label="Sponsor address"
                  id="sponsorAddress"
                  optional
                  error={form.formState.errors.sponsorAddress?.message}
                >
                  <Textarea id="sponsorAddress" rows={2} {...form.register("sponsorAddress")} />
                </Field>
              </>
            ) : null}
            <Field
              label="Mailing address"
              id="mailingAddress"
              optional
              error={form.formState.errors.mailingAddress?.message}
            >
              <Textarea id="mailingAddress" rows={2} {...form.register("mailingAddress")} />
            </Field>
            <div className="sm:col-span-2 space-y-2 rounded-xl bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">{settings.declarationText}</p>
              <Field
                label="Type the guardian's name to sign"
                id="declaredBy"
                error={form.formState.errors.declaredBy?.message}
              >
                <Input
                  id="declaredBy"
                  className="h-12"
                  placeholder={guardian || "Guardian name"}
                  {...form.register("declaredBy")}
                />
              </Field>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        {step > 0 ? (
          <Button
            type="button"
            variant="outline"
            className="h-12"
            onClick={() => setStep((current) => Math.max(current - 1, 0))}
          >
            Back
          </Button>
        ) : null}
        {isLastStep ? (
          <Button
            type="submit"
            className="h-12 text-base"
            disabled={isPending || availableClasses.length === 0}
          >
            {isPending ? "Saving…" : submitLabel}
          </Button>
        ) : (
          <Button type="button" className="h-12 text-base" onClick={() => void next()}>
            Continue
          </Button>
        )}
        {onCancel}
      </div>
    </form>
  );
}

function Field({
  label,
  id,
  error,
  hint,
  optional = false,
  children,
}: {
  label: string;
  id: string;
  error?: string | undefined;
  hint?: string | undefined;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label}{" "}
        {optional ? (
          <span className="text-xs font-normal text-muted-foreground">(optional)</span>
        ) : (
          <span className="text-destructive">*</span>
        )}
      </Label>
      {children}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-sm text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

/** Shared loader hook: the wizard needs the school's admission configuration. */
export function useAdmissionSettings() {
  return useQuery({
    queryKey: ["admission-settings"],
    queryFn: getAdmissionSettings,
  });
}
