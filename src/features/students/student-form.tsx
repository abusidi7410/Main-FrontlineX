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
import { ARMS, CLASSES } from "@/api/mock";
import { ngPhone, requiredText } from "@/lib/validation";

export const studentSchema = z.object({
  firstName: requiredText("First name"),
  lastName: requiredText("Surname"),
  admissionNumber: requiredText("Admission number", 30),
  gender: z.enum(["male", "female"]),
  dateOfBirth: requiredText("Date of birth"),
  className: requiredText("Class"),
  arm: requiredText("Arm"),
  guardianName: requiredText("Guardian name"),
  guardianPhone: ngPhone,
});

export type StudentValues = z.output<typeof studentSchema>;

export function StudentForm({
  defaultValues,
  submitLabel,
  isPending,
  onSubmit,
  cancelLink,
}: {
  defaultValues: StudentValues;
  submitLabel: string;
  isPending: boolean;
  onSubmit: (values: StudentValues) => void;
  cancelLink: React.ReactNode;
}) {
  const form = useForm<StudentValues>({
    resolver: zodResolver(studentSchema),
    defaultValues,
  });

  return (
    <form
      noValidate
      className="fn-panel space-y-4 p-5"
      onSubmit={form.handleSubmit(onSubmit)}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="First name" id="firstName" error={form.formState.errors.firstName?.message}>
          <Input id="firstName" className="h-12" {...form.register("firstName")} />
        </Field>
        <Field label="Surname" id="lastName" error={form.formState.errors.lastName?.message}>
          <Input id="lastName" className="h-12" {...form.register("lastName")} />
        </Field>
        <Field
          label="Admission number"
          id="admissionNumber"
          error={form.formState.errors.admissionNumber?.message}
        >
          <Input
            id="admissionNumber"
            className="h-12"
            placeholder="ALN/2024/001"
            {...form.register("admissionNumber")}
          />
        </Field>
        <Field label="Date of birth" id="dateOfBirth" error={form.formState.errors.dateOfBirth?.message}>
          <Input id="dateOfBirth" type="date" className="h-12" {...form.register("dateOfBirth")} />
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Class" id="className" error={form.formState.errors.className?.message}>
            <Select
              value={form.watch("className")}
              onValueChange={(value) => form.setValue("className", value)}
            >
              <SelectTrigger id="className" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLASSES.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Arm" id="arm" error={form.formState.errors.arm?.message}>
            <Select
              value={form.watch("arm")}
              onValueChange={(value) => form.setValue("arm", value)}
            >
              <SelectTrigger id="arm" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ARMS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field label="Guardian name" id="guardianName" error={form.formState.errors.guardianName?.message}>
          <Input id="guardianName" className="h-12" {...form.register("guardianName")} />
        </Field>
        <Field label="Guardian phone" id="guardianPhone" error={form.formState.errors.guardianPhone?.message}>
          <Input
            id="guardianPhone"
            inputMode="tel"
            placeholder="08012345678"
            className="h-12"
            {...form.register("guardianPhone")}
          />
        </Field>
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