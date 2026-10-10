import { useNavigate, Link } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, type Dispatch, type SetStateAction, type ReactNode } from "react";
import { useController, useForm, type UseFormReturn } from "react-hook-form";
import { z } from "zod";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  CreditCard,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { LocationMap } from "@/components/common/location-map";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSession } from "@/auth/session";
import { HOME_BY_ROLE } from "@/permissions/navigation";
import { SUBSCRIPTION_TIERS, tierById } from "@/constants/plans";
import { NIGERIAN_STATES, lgasForState } from "@/constants/nigeria";
import { emailField, ngPhone, passwordField, requiredText } from "@/lib/validation";
import { getCurrentPosition, geolocationSupported } from "@/lib/geolocation";
import { naira } from "@/lib/format";
import { registerSchool, verifySchoolPayment } from "@/services/school.service";
import { cn } from "@/lib/utils";
import type { SubscriptionTier } from "@/types";

const loginSchema = z.object({
  identifier: z.string().trim().min(1, { message: "Enter your email address or phone number" }),
  password: z.string().min(1, { message: "Enter your password" }),
});

type LoginValues = z.infer<typeof loginSchema>;

const SCHOOL_TYPES = [
  "Nursery only",
  "Nursery & Primary",
  "Primary only",
  "Primary & Secondary",
  "Secondary only",
];

const schoolSchema = z.object({
  name: requiredText("School name"),
  type: requiredText("School type"),
  address: requiredText("Address", 200),
  state: requiredText("State"),
  lga: requiredText("Local government area"),
  phone: ngPhone,
  email: emailField,
  website: z.string().trim().max(120).optional().or(z.literal("")),
  latitude: z.number().min(-90).max(90).optional(),
  longitude: z.number().min(-180).max(180).optional(),
  gpsAccuracy: z.number().nonnegative().optional(),
});

const adminSchema = z.object({
  fullName: requiredText("Full name"),
  phone: ngPhone,
  email: emailField,
  password: passwordField,
});

type SchoolValues = z.input<typeof schoolSchema>;
type AdminValues = z.input<typeof adminSchema>;

const STEPS = [
  "School information",
  "Administrator account",
  "Choose subscription",
  "Payment",
  "Verification",
  "School activated",
];

const NAVY = "hsl(var(--primary))";
const INK = "hsl(var(--foreground))";
const MUTED = "hsl(var(--muted-foreground))";
const SOFT = "hsl(var(--muted-foreground))";
const TERRACOTTA = "hsl(var(--destructive))";
const ERROR_TEXT = "hsl(var(--destructive))";

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

function FieldError({ message, id }: { message?: string | undefined; id: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1 text-[12px] leading-relaxed" style={{ color: ERROR_TEXT }}>
      {message}
    </p>
  );
}

type AuthFieldProps = {
  value: string;
  onChange: (event: unknown) => void;
  onBlur: () => void;
  name: string;
  ref: (instance: HTMLInputElement | null) => void;
};

type PasswordFieldProps = {
  id: string;
  label: ReactNode;
  labelExtra?: ReactNode;
  hint?: string;
  message?: string | undefined;
  describedBy: string;
  autoComplete: string;
  field: AuthFieldProps;
};

function PasswordField({
  id,
  label,
  labelExtra,
  hint,
  message,
  describedBy,
  autoComplete,
  field,
}: PasswordFieldProps) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={id}
          className="text-[12px] font-medium tracking-[0.02em]"
          style={{ color: MUTED }}
        >
          {label}
        </label>
        {labelExtra}
      </div>
      <div className="relative">
        <Lock
          className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2"
          style={{ color: SOFT }}
          aria-hidden="true"
        />
        <input
          id={id}
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          className={cn("auth-input pl-11 pr-14", message && "auth-input-err")}
          aria-invalid={!!message}
          aria-describedby={message ? describedBy : undefined}
          {...field}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? "Hide password" : "Show password"}
          aria-pressed={show}
          className="absolute right-2 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-xl text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          {show ? (
            <EyeOff className="size-[18px]" aria-hidden="true" />
          ) : (
            <Eye className="size-[18px]" aria-hidden="true" />
          )}
        </button>
      </div>
      {hint ? (
        <p className="text-[12px] leading-relaxed" style={{ color: SOFT }}>
          {hint}
        </p>
      ) : null}
      <FieldError id={describedBy} message={message} />
    </div>
  );
}

function AuthMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-11 shrink-0 place-items-center rounded-2xl bg-primary font-display text-sm font-bold text-primary-foreground shadow-sm",
        className,
      )}
    >
      FN
    </span>
  );
}

function AuthLockup() {
  return (
    <span className="inline-flex items-center gap-3">
      <AuthMark />
      <span className="flex flex-col text-left leading-tight">
        <span
          className="font-display text-[15px] font-semibold tracking-tight"
          style={{ color: NAVY }}
        >
          Frontline Nexus
        </span>
        <span className="text-[11px]" style={{ color: MUTED }}>
          We Develop. We Secure. We Connect.
        </span>
      </span>
    </span>
  );
}

function Headline({ children }: { children: ReactNode }) {
  return (
    <h1
      className="font-display font-semibold leading-tight tracking-[-0.01em] text-[clamp(1.375rem,2vw,1.75rem)] text-balance"
      style={{ color: INK }}
    >
      {children}
    </h1>
  );
}

function Subtext({ children }: { children: ReactNode }) {
  return (
    <p className="text-[13px] leading-relaxed" style={{ color: MUTED }}>
      {children}
    </p>
  );
}

function LoginContent({
  form,
  serverError,
  onSubmit,
  onShowRegister,
}: {
  form: UseFormReturn<LoginValues>;
  serverError: string | null;
  onSubmit: ReturnType<UseFormReturn<LoginValues>["handleSubmit"]>;
  onShowRegister: () => void;
}) {
  const { field: identifierField } = useController({
    control: form.control,
    name: "identifier",
  });
  const { field: passwordField } = useController({
    control: form.control,
    name: "password",
  });

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Headline>Sign in to your school account</Headline>
        <Subtext>
          Welcome back. Use the email address or phone number linked to your account.
        </Subtext>
      </div>

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {serverError ? (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-[13px] leading-relaxed text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{serverError}</span>
          </div>
        ) : null}

        <div className="space-y-1.5">
          <label
            htmlFor="identifier"
            className="text-[12px] font-medium tracking-[0.02em]"
            style={{ color: MUTED }}
          >
            Email or phone number <span style={{ color: TERRACOTTA }}>*</span>
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2"
              style={{ color: SOFT }}
              aria-hidden="true"
            />
            <input
              id="identifier"
              autoComplete="username"
              placeholder="you@school.edu.ng or 080..."
              className={cn(
                "auth-input pl-11",
                form.formState.errors.identifier && "auth-input-err",
              )}
              aria-invalid={!!form.formState.errors.identifier}
              aria-describedby={form.formState.errors.identifier ? "identifier-error" : undefined}
              {...identifierField}
            />
          </div>
          <FieldError
            id="identifier-error"
            message={form.formState.errors.identifier?.message ?? ""}
          />
        </div>

        <PasswordField
          id="password"
          label={
            <>
              Password <span style={{ color: TERRACOTTA }}>*</span>
            </>
          }
          labelExtra={
            <Link to="/forgot-password" className="auth-link">
              Forgot password?
            </Link>
          }
          message={form.formState.errors.password?.message ?? undefined}
          describedBy="password-error"
          autoComplete="current-password"
          field={passwordField}
        />

        <div className="flex justify-center pt-2">
          <button
            type="submit"
            className="auth-btn auth-btn-form"
            disabled={form.formState.isSubmitting}
            aria-busy={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </div>
      </form>

      <p className="border-t border-border pt-4 text-[12px] leading-relaxed text-muted-foreground">
        Staff, parents and students should use the account provided by their school.
        <br />
        Setting up a new school?{" "}
        <button
          type="button"
          onClick={onShowRegister}
          className="auth-link font-semibold"
          style={{ color: NAVY }}
        >
          Create a school account
        </button>
      </p>
    </div>
  );
}

function RegisterContent({
  schoolForm,
  adminForm,
  step,
  setStep,
  schoolData,
  adminData,
  tierId,
  setTierId,
  tier,
  onSchoolSubmit,
  onAdminSubmit,
  submitting,
  startPayment,
  verifying,
  paymentRef,
  onShowLogin,
}: {
  schoolForm: UseFormReturn<SchoolValues>;
  adminForm: UseFormReturn<AdminValues>;
  step: number;
  setStep: Dispatch<SetStateAction<number>>;
  schoolData: SchoolValues | null;
  adminData: AdminValues | null;
  tierId: string;
  setTierId: (id: string) => void;
  tier: SubscriptionTier;
  onSchoolSubmit: (values: SchoolValues) => void;
  onAdminSubmit: (values: AdminValues) => void;
  submitting: boolean;
  startPayment: () => void;
  verifying: boolean;
  paymentRef: string | null;
  onShowLogin: () => void;
}) {
  const { field: nameField } = useController({ control: schoolForm.control, name: "name" });
  const { field: addressField } = useController({ control: schoolForm.control, name: "address" });
  const { field: phoneField } = useController({ control: schoolForm.control, name: "phone" });
  const { field: emailField } = useController({ control: schoolForm.control, name: "email" });
  const { field: websiteField } = useController({ control: schoolForm.control, name: "website" });
  const { field: fullNameField } = useController({ control: adminForm.control, name: "fullName" });
  const { field: adminPhoneField } = useController({ control: adminForm.control, name: "phone" });
  const { field: adminEmailField } = useController({ control: adminForm.control, name: "email" });
  const { field: adminPasswordField } = useController({
    control: adminForm.control,
    name: "password",
  });

  const [geoBusy, setGeoBusy] = useState(false);
  const [geoMessage, setGeoMessage] = useState<string | null>(null);
  const schoolLatitude = schoolForm.watch("latitude");
  const schoolLongitude = schoolForm.watch("longitude");
  const schoolHasLocation = schoolLatitude != null && schoolLongitude != null;
  const selectedState = schoolForm.watch("state");
  const lgaOptions = lgasForState(selectedState);

  const captureLocation = async () => {
    setGeoBusy(true);
    setGeoMessage(null);
    try {
      const fix = await getCurrentPosition();
      schoolForm.setValue("latitude", Number(fix.latitude.toFixed(6)), { shouldValidate: true });
      schoolForm.setValue("longitude", Number(fix.longitude.toFixed(6)), { shouldValidate: true });
      schoolForm.setValue("gpsAccuracy", Math.round(fix.accuracy), { shouldValidate: true });
      setGeoMessage(`Location captured (accurate to about ${Math.round(fix.accuracy)} m).`);
    } catch (error) {
      setGeoMessage(error instanceof Error ? error.message : "We could not get your location.");
    } finally {
      setGeoBusy(false);
    }
  };

  const clearLocation = () => {
    schoolForm.setValue("latitude", undefined, { shouldValidate: true });
    schoolForm.setValue("longitude", undefined, { shouldValidate: true });
    schoolForm.setValue("gpsAccuracy", undefined, { shouldValidate: true });
    setGeoMessage(null);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Headline>Create School</Headline>
        <Subtext>Set up your school account — it only takes a few minutes.</Subtext>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p
          className="text-[11px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: NAVY }}
        >
          Step {Math.min(step + 1, STEPS.length)} of {STEPS.length}
        </p>
        <p className="text-[12px] font-medium" style={{ color: MUTED }}>
          {STEPS[step]}
        </p>
      </div>
      <Progress
        value={((step + 1) / STEPS.length) * 100}
        className="h-1.5 rounded-full bg-muted [&>div]:bg-primary"
      />

      {step === 0 ? (
        <form
          noValidate
          className="space-y-4"
          onSubmit={schoolForm.handleSubmit((values) => {
            onSchoolSubmit(values);
          })}
        >
          <div className="space-y-1.5">
            <label
              htmlFor="name"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              School name <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="name"
              className={cn("auth-input", schoolForm.formState.errors.name && "auth-input-err")}
              aria-invalid={!!schoolForm.formState.errors.name}
              aria-describedby={schoolForm.formState.errors.name ? "name-error" : undefined}
              {...nameField}
            />
            <FieldError id="name-error" message={schoolForm.formState.errors.name?.message ?? ""} />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="type"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              School type <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <Select
              onValueChange={(value) =>
                schoolForm.setValue("type", value, { shouldValidate: true })
              }
              value={schoolForm.watch("type")}
            >
              <SelectTrigger
                id="type"
                className="auth-input cursor-pointer px-4 text-[13px] text-foreground"
              >
                <SelectValue placeholder="Select school type" />
              </SelectTrigger>
              <SelectContent>
                {SCHOOL_TYPES.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError id="type-error" message={schoolForm.formState.errors.type?.message ?? ""} />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="address"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Street address <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="address"
              className={cn("auth-input", schoolForm.formState.errors.address && "auth-input-err")}
              aria-invalid={!!schoolForm.formState.errors.address}
              aria-describedby={schoolForm.formState.errors.address ? "address-error" : undefined}
              {...addressField}
            />
            <FieldError
              id="address-error"
              message={schoolForm.formState.errors.address?.message ?? ""}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="state"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              State <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <Select
              onValueChange={(value) => {
                schoolForm.setValue("state", value, { shouldValidate: true });
                schoolForm.setValue("lga", "", { shouldValidate: true });
              }}
              value={schoolForm.watch("state")}
            >
              <SelectTrigger
                id="state"
                className="auth-input cursor-pointer px-4 text-[13px] text-foreground"
              >
                <SelectValue placeholder="Select state" />
              </SelectTrigger>
              <SelectContent>
                {NIGERIAN_STATES.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError
              id="state-error"
              message={schoolForm.formState.errors.state?.message ?? ""}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="lga"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Local government area <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <Select
              disabled={!selectedState}
              onValueChange={(value) =>
                schoolForm.setValue("lga", value, { shouldValidate: true })
              }
              value={schoolForm.watch("lga")}
            >
              <SelectTrigger
                id="lga"
                className={cn(
                  "auth-input cursor-pointer px-4 text-[13px] text-foreground",
                  schoolForm.formState.errors.lga && "auth-input-err",
                )}
                aria-invalid={!!schoolForm.formState.errors.lga}
              >
                <SelectValue placeholder={selectedState ? "Select LGA" : "Select a state first"} />
              </SelectTrigger>
              <SelectContent>
                {lgaOptions.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError id="lga-error" message={schoolForm.formState.errors.lga?.message ?? ""} />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="phone"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              School phone number <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="phone"
              inputMode="tel"
              placeholder="08012345678"
              className={cn("auth-input", schoolForm.formState.errors.phone && "auth-input-err")}
              aria-invalid={!!schoolForm.formState.errors.phone}
              aria-describedby={schoolForm.formState.errors.phone ? "phone-error" : undefined}
              {...phoneField}
            />
            <p className="text-[11.5px]" style={{ color: SOFT }}>
              Nigerian number, e.g. 08012345678 or +2348012345678.
            </p>
            <FieldError
              id="phone-error"
              message={schoolForm.formState.errors.phone?.message ?? ""}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="school-email"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              School email <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="school-email"
              type="email"
              className={cn("auth-input", schoolForm.formState.errors.email && "auth-input-err")}
              aria-invalid={!!schoolForm.formState.errors.email}
              aria-describedby={
                schoolForm.formState.errors.email ? "school-email-error" : undefined
              }
              {...emailField}
            />
            <FieldError
              id="school-email-error"
              message={schoolForm.formState.errors.email?.message ?? ""}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="website"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Website{" "}
              <span className="font-normal" style={{ color: SOFT }}>
                (optional)
              </span>
            </label>
            <input
              id="website"
              placeholder="www.yourschool.edu.ng"
              className="auth-input"
              {...websiteField}
            />
          </div>

          <div className="space-y-2 rounded-xl border border-[#E2DCCE] p-3">
            <div>
              <p className="text-[12px] font-medium tracking-[0.02em]" style={{ color: MUTED }}>
                School location{" "}
                <span className="font-normal" style={{ color: SOFT }}>
                  (optional, but recommended)
                </span>
              </p>
              <p className="mt-0.5 text-[11.5px] leading-snug" style={{ color: SOFT }}>
                Captured once, it lets us confirm staff check-ins are on campus. You can add or
                change it later in Settings.
              </p>
            </div>
            {schoolHasLocation ? (
              <LocationMap
                latitude={schoolLatitude ?? null}
                longitude={schoolLongitude ?? null}
                interactive
                height={180}
                radiusMeters={150}
                onChange={(lat, lng) => {
                  schoolForm.setValue("latitude", Number(lat.toFixed(6)), { shouldValidate: true });
                  schoolForm.setValue("longitude", Number(lng.toFixed(6)), {
                    shouldValidate: true,
                  });
                }}
              />
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void captureLocation()}
                disabled={geoBusy || !geolocationSupported()}
                className="auth-btn auth-btn-form !mt-0 disabled:opacity-60"
              >
                {geoBusy
                  ? "Getting location…"
                  : schoolHasLocation
                    ? "Re-capture location"
                    : "Use my current location"}
              </button>
              {schoolHasLocation ? (
                <button
                  type="button"
                  onClick={clearLocation}
                  className="text-[12px] font-medium"
                  style={{ color: MUTED }}
                >
                  Clear
                </button>
              ) : null}
            </div>
            {geoMessage ? (
              <p className="text-[11.5px]" style={{ color: SOFT }}>
                {geoMessage}
              </p>
            ) : null}
            {schoolHasLocation ? (
              <p className="text-[11.5px]" style={{ color: SOFT }}>
                Drag the pin or tap the map to fine-tune the exact campus point.
              </p>
            ) : null}
          </div>

          <div className="flex justify-center pt-2">
            <button type="submit" className="auth-btn auth-btn-form">
              Continue to administrator details
            </button>
          </div>
        </form>
      ) : null}

      {step === 1 ? (
        <form
          noValidate
          className="space-y-4"
          onSubmit={adminForm.handleSubmit((values) => {
            onAdminSubmit(values);
          })}
        >
          <p
            className="auth-inset border border-[#E2DCCE] p-4 text-[12.5px] leading-relaxed"
            style={{ color: MUTED }}
          >
            This account becomes the school administrator. Teachers, bursars, parents and students
            are invited from inside Frontline Nexus afterwards.
          </p>
          <div className="space-y-1.5">
            <label
              htmlFor="fullName"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Full name <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="fullName"
              className={cn("auth-input", adminForm.formState.errors.fullName && "auth-input-err")}
              aria-invalid={!!adminForm.formState.errors.fullName}
              aria-describedby={adminForm.formState.errors.fullName ? "fullName-error" : undefined}
              {...fullNameField}
            />
            <FieldError
              id="fullName-error"
              message={adminForm.formState.errors.fullName?.message ?? ""}
            />
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor="admin-phone"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Phone number <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="admin-phone"
              inputMode="tel"
              placeholder="08012345678"
              className={cn("auth-input", adminForm.formState.errors.phone && "auth-input-err")}
              aria-invalid={!!adminForm.formState.errors.phone}
              aria-describedby={adminForm.formState.errors.phone ? "admin-phone-error" : undefined}
              {...adminPhoneField}
            />
            <FieldError
              id="admin-phone-error"
              message={adminForm.formState.errors.phone?.message ?? ""}
            />
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor="admin-email"
              className="text-[12px] font-medium tracking-[0.02em]"
              style={{ color: MUTED }}
            >
              Email address <span style={{ color: TERRACOTTA }}>*</span>
            </label>
            <input
              id="admin-email"
              type="email"
              className={cn("auth-input", adminForm.formState.errors.email && "auth-input-err")}
              aria-invalid={!!adminForm.formState.errors.email}
              aria-describedby={adminForm.formState.errors.email ? "admin-email-error" : undefined}
              {...adminEmailField}
            />
            <FieldError
              id="admin-email-error"
              message={adminForm.formState.errors.email?.message ?? ""}
            />
          </div>
          <PasswordField
            id="admin-password"
            label={
              <>
                Password <span style={{ color: TERRACOTTA }}>*</span>
              </>
            }
            hint="At least 8 characters, including a letter and a number."
            message={adminForm.formState.errors.password?.message ?? undefined}
            describedBy="admin-password-error"
            autoComplete="new-password"
            field={adminPasswordField}
          />
          <div className="flex flex-col items-center gap-2.5 pt-2">
            <button type="submit" className="auth-btn auth-btn-form">
              Continue to subscription
            </button>
            <button
              type="button"
              className="auth-btn-ghost auth-btn-form"
              onClick={() => setStep(0)}
            >
              Back
            </button>
          </div>
        </form>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          <Subtext>
            Choose the tier that matches your current enrolment. You can change tier at any time and
            grow within it during a billing period.
          </Subtext>
          <ul className="space-y-2.5">
            {SUBSCRIPTION_TIERS.map((option) => {
              const selected = option.id === tierId;
              return (
                <li key={option.id}>
                  <button
                    type="button"
                    onClick={() => setTierId(option.id)}
                    aria-pressed={selected}
                    className="auth-tier"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-semibold" style={{ color: INK }}>
                        {option.label}
                      </span>
                      {selected ? (
                        <Check className="size-4" style={{ color: NAVY }} aria-hidden="true" />
                      ) : null}
                    </span>
                    <span
                      className="mt-0.5 block font-display text-[15px] font-semibold"
                      style={{ color: NAVY }}
                    >
                      {naira(option.monthlyPrice)}
                      <span className="text-[11px] font-normal" style={{ color: MUTED }}>
                        {" "}
                        /month
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-col items-center gap-2.5 pt-1">
            <button type="button" className="auth-btn auth-btn-form" onClick={() => setStep(3)}>
              Continue to payment
            </button>
            <button
              type="button"
              className="auth-btn-ghost auth-btn-form"
              onClick={() => setStep(1)}
            >
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="space-y-4">
          <div className="auth-inset border border-[#E2DCCE] p-4">
            <h3
              className="text-[12px] font-semibold uppercase tracking-[0.12em]"
              style={{ color: NAVY }}
            >
              Order summary
            </h3>
            <dl className="mt-3 space-y-2 text-[13px]">
              <div className="flex justify-between gap-3">
                <dt style={{ color: MUTED }}>School</dt>
                <dd className="truncate font-medium" style={{ color: INK }}>
                  {schoolData?.name}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt style={{ color: MUTED }}>Administrator</dt>
                <dd className="truncate font-medium" style={{ color: INK }}>
                  {adminData?.fullName}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt style={{ color: MUTED }}>Plan</dt>
                <dd className="font-medium" style={{ color: INK }}>
                  {tier.label}
                </dd>
              </div>
              <div className="flex justify-between gap-3 border-t border-border pt-2">
                <dt className="font-medium" style={{ color: INK }}>
                  Due today
                </dt>
                <dd className="font-display text-base font-semibold" style={{ color: NAVY }}>
                  {naira(tier.monthlyPrice)}
                </dd>
              </div>
            </dl>
          </div>
          <div className="auth-inset flex gap-3 border border-border p-4 text-[12.5px] leading-relaxed text-muted-foreground">
            <ShieldCheck
              className="mt-0.5 size-4 shrink-0"
              style={{ color: NAVY }}
              aria-hidden="true"
            />
            <p>
              Payment is handled by our payment provider. Your school activates automatically the
              moment the payment is confirmed — no manual approval needed.
            </p>
          </div>
          <div className="flex flex-col items-center gap-2.5">
            <button
              type="button"
              className="auth-btn auth-btn-form"
              onClick={startPayment}
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Starting payment…
                </>
              ) : (
                <>
                  <CreditCard className="size-4" aria-hidden="true" /> Pay{" "}
                  {naira(tier.monthlyPrice)}
                </>
              )}
            </button>
            <button
              type="button"
              className="auth-btn-ghost auth-btn-form"
              onClick={() => setStep(2)}
            >
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === 4 ? (
        <div className="flex flex-col items-center gap-3 px-2 py-10 text-center">
          <Loader2 className="size-7 animate-spin" style={{ color: NAVY }} aria-hidden="true" />
          <h3 className="text-[15px] font-semibold" style={{ color: INK }}>
            {verifying ? "Verifying your payment…" : "Payment pending"}
          </h3>
          <p className="max-w-[300px] text-[13px] leading-relaxed" style={{ color: MUTED }}>
            {verifying
              ? "We're confirming your payment with the provider. This usually takes a few seconds — you can keep this page open."
              : "Payment verification is not available yet. Your school will stay inactive until payment is confirmed. Save this reference and contact support for next steps."}
          </p>
          {paymentRef ? (
            <p className="text-[12px]" style={{ color: MUTED }}>
              Reference: {paymentRef}
            </p>
          ) : null}
        </div>
      ) : null}

      {step === 5 ? (
        <div className="px-2 py-8 text-center">
          <CheckCircle2 className="mx-auto size-11" style={{ color: NAVY }} aria-hidden="true" />
          <h3 className="mt-4 font-display text-[22px] font-semibold" style={{ color: INK }}>
            {schoolData?.name} is activated
          </h3>
          <p
            className="mx-auto mt-2 max-w-[320px] text-[13px] leading-relaxed"
            style={{ color: MUTED }}
          >
            Your payment was confirmed and your school is live on the {tier.label} plan. Sign in to
            finish setting up classes, subjects, students and fees.
          </p>
          <div className="mt-6 flex flex-col items-center gap-2.5">
            <Link to="/login" className="auth-btn auth-btn-form">
              Sign in to your school
            </Link>
            <Link to="/" className="auth-btn-ghost auth-btn-form">
              Back to home
            </Link>
          </div>
        </div>
      ) : null}

      <p className="border-t border-border pt-4 text-[12px] leading-relaxed text-muted-foreground">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onShowLogin}
          className="auth-link font-semibold"
          style={{ color: NAVY }}
        >
          Sign in
        </button>
      </p>
    </div>
  );
}

export function AuthScreens({
  initialMode,
  redirectTo,
  initialTier,
  initialServerError,
}: {
  initialMode: "login" | "register";
  redirectTo?: string | undefined;
  initialTier?: string | undefined;
  initialServerError?: string | undefined;
}) {
  const { signIn, session, status } = useSession();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const register = mode === "register";

  // Seeded from the redirect that brought the user here: when the server ends a
  // session for a reason worth stating (a suspended school), the login page
  // says so instead of looking like an inexplicable logout.
  const [serverError, setServerError] = useState<string | null>(initialServerError ?? null);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: "", password: "" },
  });

  useEffect(() => {
    if (initialMode !== "login") return;
    if (status === "authenticated" && session) {
      void navigate({
        to: (redirectTo || HOME_BY_ROLE[session.user.role]) as never,
        replace: true,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, session, navigate, redirectTo]);

  const onSubmit = form.handleSubmit(async (values) => {
    setServerError(null);
    try {
      const next = await signIn(values.identifier, values.password);
      await navigate({
        to: (redirectTo || HOME_BY_ROLE[next.user.role]) as never,
        replace: true,
      });
    } catch (error) {
      setServerError(
        error instanceof Error ? error.message : "We couldn't sign you in. Please try again.",
      );
    }
  });

  const [step, setStep] = useState(0);
  const [schoolData, setSchoolData] = useState<SchoolValues | null>(null);
  const [adminData, setAdminData] = useState<AdminValues | null>(null);
  const [tierId, setTierId] = useState(initialTier ?? "t400");
  const [paymentRef, setPaymentRef] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const schoolForm = useForm<SchoolValues>({
    resolver: zodResolver(schoolSchema),
    defaultValues: {
      name: "",
      type: "",
      address: "",
      state: "",
      lga: "",
      phone: "",
      email: "",
      website: "",
      latitude: undefined,
      longitude: undefined,
      gpsAccuracy: undefined,
    },
  });
  const adminForm = useForm<AdminValues>({
    resolver: zodResolver(adminSchema),
    defaultValues: { fullName: "", phone: "", email: "", password: "" },
  });

  const tier = tierById(tierId) ?? SUBSCRIPTION_TIERS[0]!;

  const startPayment = async () => {
    if (!schoolData || !adminData) return;
    setSubmitting(true);
    try {
      const result = await registerSchool({
        school: { ...schoolData, ...(schoolData.website ? { website: schoolData.website } : {}) },
        admin: adminData,
        tierId,
      });
      setPaymentRef(result.paymentRef);
      setStep(4);
      setVerifying(true);
      const verification = await verifySchoolPayment(result.paymentRef);
      setVerifying(false);
      if (verification.status === "verified") setStep(5);
    } finally {
      setSubmitting(false);
    }
  };

  const toggle = () => setMode((m) => (m === "login" ? "register" : "login"));

  useEffect(() => {
    const split = window.matchMedia("(min-width: 1024px)").matches;
    const suffix = split ? "" : "-compact";
    const id = register ? `auth-register-pane${suffix}` : `auth-login-pane${suffix}`;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(id)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mode, register]);

  const splitContentClasses = "m-auto w-full px-8 py-12";

  return (
    <div className="auth-page relative flex min-h-screen flex-col">
      <div className="relative z-10 mx-auto flex w-full flex-1 flex-col items-center justify-center px-3 py-5 sm:px-6 sm:py-6">
        <div className="mb-5">
          <AuthLockup />
        </div>

        {/* Single-column composition: phones, tablets in portrait, and any
            viewport where the split panel would feel cramped. Height follows
            the content and the page scrolls naturally. */}
        <div className="relative w-full max-w-[500px] lg:hidden" data-auth-compact>
          <div className="auth-card relative overflow-hidden px-6 py-8 sm:px-8 sm:py-9">
            <div key={register ? "register" : "login"} className="fn-slide-up relative">
              {register ? (
                <section
                  id="auth-register-pane-compact"
                  tabIndex={-1}
                  className="focus:outline-none"
                >
                  <RegisterContent
                    schoolForm={schoolForm}
                    adminForm={adminForm}
                    step={step}
                    setStep={setStep}
                    schoolData={schoolData}
                    adminData={adminData}
                    tierId={tierId}
                    setTierId={setTierId}
                    tier={tier}
                    onSchoolSubmit={(values) => {
                      setSchoolData(values);
                      setStep(1);
                    }}
                    onAdminSubmit={(values) => {
                      setAdminData(values);
                      setStep(2);
                    }}
                    submitting={submitting}
                    startPayment={() => void startPayment()}
                    verifying={verifying}
                    paymentRef={paymentRef}
                    onShowLogin={toggle}
                  />
                </section>
              ) : (
                <section id="auth-login-pane-compact" tabIndex={-1} className="focus:outline-none">
                  <LoginContent
                    form={form}
                    serverError={serverError}
                    onSubmit={onSubmit}
                    onShowRegister={toggle}
                  />
                </section>
              )}
            </div>
          </div>
        </div>

        {/* Split-panel composition: desktop and wide landscape. Two equal grid
            columns on the same ivory surface; each pane scrolls internally
            when the frame is shorter than its form, and the page scrolls
            naturally as a last resort. */}
        <div
          className="hidden w-full lg:block"
          style={{ width: "min(1000px, calc(100vw - 80px))" }}
        >
          <div
            data-auth-frame
            role="group"
            aria-label="Authentication"
            className="auth-frame relative grid grid-cols-2 overflow-hidden"
          >
            {/* Login pane */}
            <section
              id="auth-login-pane"
              tabIndex={-1}
              data-auth-pane
              aria-hidden={register}
              inert={register}
              className="z-10 flex min-h-0 flex-col overflow-y-auto overscroll-contain focus:outline-none"
            >
              <div
                className={cn(
                  splitContentClasses,
                  "max-w-[360px]",
                  "transition-[transform,opacity] duration-[1150ms]",
                  register ? "-translate-x-4 opacity-0" : "translate-x-0 opacity-100",
                )}
                style={{ transitionTimingFunction: EASE }}
              >
                <LoginContent
                  form={form}
                  serverError={serverError}
                  onSubmit={onSubmit}
                  onShowRegister={toggle}
                />
              </div>
            </section>

            {/* Create School pane */}
            <section
              id="auth-register-pane"
              tabIndex={-1}
              data-auth-pane
              aria-hidden={!register}
              inert={!register}
              className="z-10 flex min-h-0 flex-col overflow-y-auto overscroll-contain focus:outline-none"
            >
              <div
                className={cn(
                  splitContentClasses,
                  "max-w-[400px]",
                  "transition-[transform,opacity] duration-[1150ms]",
                  register ? "translate-x-0 opacity-100" : "translate-x-4 opacity-0",
                )}
                style={{ transitionTimingFunction: EASE }}
              >
                <RegisterContent
                  schoolForm={schoolForm}
                  adminForm={adminForm}
                  step={step}
                  setStep={setStep}
                  schoolData={schoolData}
                  adminData={adminData}
                  tierId={tierId}
                  setTierId={setTierId}
                  tier={tier}
                  onSchoolSubmit={(values) => {
                    setSchoolData(values);
                    setStep(1);
                  }}
                  onAdminSubmit={(values) => {
                    setAdminData(values);
                    setStep(2);
                  }}
                  submitting={submitting}
                  startPayment={() => void startPayment()}
                  verifying={verifying}
                  paymentRef={paymentRef}
                  onShowLogin={toggle}
                />
              </div>
            </section>

            {/* Sliding welcome panel */}
            <div
              data-auth-welcome
              className={cn(
                "auth-welcome absolute inset-y-0 left-1/2 z-30 w-1/2 overflow-hidden rounded-[20px]",
                "transition-transform duration-[1250ms]",
                register ? "-translate-x-full" : "translate-x-0",
              )}
              style={{ transitionTimingFunction: EASE }}
            >
              {/* New school welcome panel */}
              <div
                className={cn(
                  "absolute inset-0 flex flex-col items-center justify-center gap-7 px-10 text-center transition-[opacity,transform] duration-[900ms]",
                  register
                    ? "pointer-events-none translate-y-1 opacity-0"
                    : "translate-y-0 opacity-100",
                )}
                inert={register}
              >
                <div>
                  <h2
                    className="font-display text-[clamp(1.5rem,1.8vw,1.75rem)] font-semibold leading-tight text-balance"
                    style={{ color: INK }}
                  >
                    Welcome to Frontline Nexus
                  </h2>
                  <p
                    className="mx-auto mt-3 max-w-[250px] text-[13px] leading-relaxed"
                    style={{ color: MUTED }}
                  >
                    Manage your school in one secure, easy-to-use place.
                  </p>
                </div>
                <button type="button" onClick={toggle} className="auth-btn-ghost">
                  Create a school account
                </button>
              </div>

              {/* Welcome Back (visible while panel rests over the left half) */}
              <div
                className={cn(
                  "absolute inset-0 flex flex-col items-center justify-center gap-7 px-10 text-center transition-[opacity,transform] duration-[900ms]",
                  register
                    ? "translate-y-0 opacity-100"
                    : "pointer-events-none translate-y-1 opacity-0",
                )}
                inert={!register}
              >
                <div>
                  <h2
                    className="font-display text-[clamp(1.5rem,1.8vw,1.75rem)] font-semibold leading-tight text-balance"
                    style={{ color: INK }}
                  >
                    Already have an account?
                  </h2>
                  <p
                    className="mx-auto mt-3 max-w-[260px] text-[13px] leading-relaxed"
                    style={{ color: MUTED }}
                  >
                    Sign in with the email or phone number linked to your school.
                  </p>
                </div>
                <button type="button" onClick={toggle} className="auth-btn-ghost">
                  Sign in
                </button>
              </div>
            </div>
          </div>
        </div>

        <p
          className="mt-6 max-w-md px-4 text-center text-[11px] leading-relaxed"
          style={{ color: MUTED }}
        >
          Frontline Nexus — We Develop. We Secure. We Connect. Your school's data stays private,
          secure and yours.
        </p>
      </div>
    </div>
  );
}
