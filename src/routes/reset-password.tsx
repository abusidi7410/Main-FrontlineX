import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Loader2, Lock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthLayout } from "@/components/layout/auth-layout";
import { passwordField } from "@/lib/validation";
import { resetPassword } from "@/services/auth.service";

export const Route = createFileRoute("/reset-password")({
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search["token"] as string) ?? "",
  }),
  head: () => ({
    meta: [
      { title: "Set a new password — Frontline Nexus" },
      { name: "description", content: "Choose a new password for your Frontline Nexus account." },
      { property: "og:title", content: "Set a new password — Frontline Nexus" },
      {
        property: "og:description",
        content: "Choose a new password for your Frontline Nexus account.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ResetPasswordPage,
});

const schema = z
  .object({ password: passwordField, confirm: z.string() })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Both passwords must match",
  });

function ResetPasswordPage() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const form = useForm<{ password: string; confirm: string }>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    await resetPassword(token, values.password);
    toast.success("Password updated. Please sign in with your new password.");
    await navigate({ to: "/login", search: {}, replace: true });
  });

  return (
    <AuthLayout
      title="Set a new password"
      description="Choose a password you haven't used on this account before."
      footer={
        <Link to="/login" search={{}} className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="password">
            New password <span className="text-destructive">*</span>
          </Label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/70"
              aria-hidden="true"
            />
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              className="h-12 pl-10"
              {...form.register("password")}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            At least 8 characters, including a letter and a number.
          </p>
          {form.formState.errors.password ? (
            <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">
            Confirm new password <span className="text-destructive">*</span>
          </Label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/70"
              aria-hidden="true"
            />
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              className="h-12 pl-10"
              {...form.register("confirm")}
            />
          </div>
          {form.formState.errors.confirm ? (
            <p className="text-sm text-destructive">{form.formState.errors.confirm.message}</p>
          ) : null}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="mr-2 size-5 animate-spin" aria-hidden="true" /> Updating password…
            </>
          ) : (
            "Update password"
          )}
        </Button>
      </form>
    </AuthLayout>
  );
}
