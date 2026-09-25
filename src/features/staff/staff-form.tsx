import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
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
import { emailField, ngPhone, requiredText } from "@/lib/validation";
import type { StaffInput, StaffRole } from "@/services/staff.service";
import type { StaffMember } from "@/types";

const STAFF_ROLES: { value: StaffRole; label: string }[] = [
  { value: "teacher", label: "Teacher" },
  { value: "accountant", label: "Bursar / Accountant" },
  { value: "secretary", label: "School Secretary" },
  { value: "principal", label: "Principal" },
];

// eslint-disable-next-line react-refresh/only-export-components
export const staffSchema = z.object({
  fullName: requiredText("Full name"),
  email: emailField,
  phone: ngPhone,
  role: z.enum(["teacher", "accountant", "secretary", "principal"]),
  subjects: z.string().trim(),
  classes: z.string().trim(),
});

export type StaffValues = z.input<typeof staffSchema>;

const splitList = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

// eslint-disable-next-line react-refresh/only-export-components
export function toStaffInput(values: StaffValues): StaffInput {
  const role = values.role as StaffRole;
  return {
    fullName: values.fullName,
    email: values.email,
    phone: values.phone,
    role,
    subjects: role === "teacher" ? splitList(values.subjects) : [],
    classes: role === "teacher" ? splitList(values.classes) : [],
  };
}

// eslint-disable-next-line react-refresh/only-export-components
export function toStaffFormValues(
  member: Pick<StaffMember, "fullName" | "email" | "phone" | "role" | "subjects" | "classes">,
): StaffValues {
  return {
    fullName: member.fullName,
    email: member.email,
    phone: member.phone,
    role: member.role as StaffValues["role"],
    subjects: member.subjects.join(", "),
    classes: member.classes.join(", "),
  };
}

export function StaffForm({
  defaultValues,
  submitLabel,
  isPending,
  onSubmit,
  cancelLink,
}: {
  defaultValues: StaffValues;
  submitLabel: string;
  isPending: boolean;
  onSubmit: (values: StaffValues) => void;
  cancelLink: React.ReactNode;
}) {
  const form = useForm<StaffValues>({
    resolver: zodResolver(staffSchema),
    defaultValues,
  });

  const role = form.watch("role");
  const isTeacher = role === "teacher";

  return (
    <form noValidate className="fn-panel space-y-4 p-5" onSubmit={form.handleSubmit(onSubmit)}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" id="fullName" error={form.formState.errors.fullName?.message}>
          <Input
            id="fullName"
            className="h-12"
            placeholder="e.g. Mrs. Aisha Bello"
            {...form.register("fullName")}
          />
        </Field>
        <Field label="Role" id="role" error={form.formState.errors.role?.message}>
          <Select
            value={form.watch("role")}
            onValueChange={(value) => form.setValue("role", value as StaffRole)}
          >
            <SelectTrigger id="role" className="h-12">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STAFF_ROLES.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Email address" id="email" error={form.formState.errors.email?.message}>
          <Input
            id="email"
            type="email"
            className="h-12"
            placeholder="aisha.bello@alnoor.edu.ng"
            {...form.register("email")}
          />
        </Field>
        <Field label="Phone" id="phone" error={form.formState.errors.phone?.message}>
          <Input
            id="phone"
            inputMode="tel"
            className="h-12"
            placeholder="08012345678"
            {...form.register("phone")}
          />
        </Field>
        {isTeacher ? (
          <>
            <Field label="Subjects" id="subjects" error={form.formState.errors.subjects?.message}>
              <Input
                id="subjects"
                className="h-12"
                placeholder="Mathematics, English Language"
                {...form.register("subjects")}
              />
              <p className="text-sm text-muted-foreground">
                Separate multiple subjects with commas.
              </p>
            </Field>
            <Field label="Classes" id="classes" error={form.formState.errors.classes?.message}>
              <Input
                id="classes"
                className="h-12"
                placeholder="JSS 2A, Primary 5A"
                {...form.register("classes")}
              />
              <p className="text-sm text-muted-foreground">
                Separate multiple classes with commas.
              </p>
            </Field>
          </>
        ) : null}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" className="h-12 text-base" disabled={isPending}>
          {isPending ? "Saving…" : submitLabel}
        </Button>
        {cancelLink}
      </div>
    </form>
  );
}

function Field({
  label,
  id,
  error,
  children,
}: {
  label: string;
  id: string;
  error?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label} <span className="text-destructive">*</span>
      </Label>
      {children}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
