import { createFileRoute, Link } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { CheckCircle2, Loader2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthLayout } from "@/components/layout/auth-layout";
import { emailField } from "@/lib/validation";
import { requestPasswordReset } from "@/services/auth.service";

export const Route = createFileRoute("/forgot-password")({
  head: () => ({
    meta: [
      { title: "Reset your password — Frontline Nexus" },
      {
        name: "description",
        content: "Request a password reset link for your Frontline Nexus account.",
      },
      { property: "og:title", content: "Reset your password — Frontline Nexus" },
      {
        property: "og:description",
        content: "Request a password reset link for your Frontline Nexus account.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ForgotPasswordPage,
});

const schema = z.object({ email: emailField });

function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const form = useForm<{ email: string }>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    await requestPasswordReset(values.email);
    setSent(values.email);
  });

  if (sent) {
    return (
      <AuthLayout
        title="Check your email"
        description={`We sent password reset instructions to ${sent}.`}
      >
        <div className="flex gap-3 rounded-2xl border border-success/30 bg-success-soft/70 p-4 backdrop-blur-sm">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden="true" />
          <p className="text-sm leading-relaxed">
            The link is valid for 30 minutes. If it doesn't arrive, check your spam folder or ask
            your school administrator to confirm the email on your account.
          </p>
        </div>
        <Button asChild variant="outline" className="mt-7 h-12 w-full">
          <Link to="/login" search={{}}>
            Back to sign in
          </Link>
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Forgot your password?"
      description="Enter the email address on your account and we'll send you a reset link."
      footer={
        <Link to="/login" search={{}} className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="email">
            Email address <span className="text-destructive">*</span>
          </Label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/70"
              aria-hidden="true"
            />
            <Input
              id="email"
              type="email"
              autoComplete="email"
              className="h-12 pl-10"
              aria-invalid={!!form.formState.errors.email}
              aria-describedby={form.formState.errors.email ? "email-error" : undefined}
              {...form.register("email")}
            />
          </div>
          {form.formState.errors.email ? (
            <p id="email-error" className="text-sm text-destructive">
              {form.formState.errors.email.message}
            </p>
          ) : null}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="mr-2 size-5 animate-spin" aria-hidden="true" /> Sending link…
            </>
          ) : (
            "Send reset link"
          )}
        </Button>
      </form>
    </AuthLayout>
  );
}
