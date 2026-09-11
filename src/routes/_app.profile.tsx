import { createFileRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { PageHeader } from "@/components/common/page-header";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/auth/session";
import { ROLE_LABELS } from "@/permissions";
import { initials, titleCase } from "@/lib/format";
import { ngPhone, passwordField, requiredText } from "@/lib/validation";
import { changePassword, updateProfile } from "@/services/auth.service";

export const Route = createFileRoute("/_app/profile")({
  head: () => ({
    meta: [
      { title: "My profile — Frontline Nexus" },
      {
        name: "description",
        content: "Your Frontline Nexus account details, role and permissions.",
      },
      { property: "og:title", content: "My profile — Frontline Nexus" },
      { property: "og:description", content: "Your account details, role and permissions." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ProfilePage,
});

const profileSchema = z.object({
  fullName: requiredText("Full name", 120),
  phone: ngPhone,
});

const passwordSchema = z
  .object({
    current: passwordField,
    next: passwordField,
    confirm: z.string().min(1, { message: "Repeat your new password" }),
  })
  .refine((v) => v.next === v.confirm, {
    message: "The two passwords do not match.",
    path: ["confirm"],
  });

function FieldError({ children }: { children: ReactNode }) {
  return <p className="text-sm text-destructive">{children}</p>;
}

function ProfilePage() {
  const { session, updateUser } = useSession();
  const user = session?.user;
  const [fullName, setFullName] = useState(user?.fullName ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [profileErrors, setProfileErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [passwordErrors, setPasswordErrors] = useState<Record<string, string>>({});
  const [changing, setChanging] = useState(false);

  const saveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = profileSchema.safeParse({ fullName, phone });
    if (!parsed.success) {
      const errs: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as string;
        if (!errs[key] && key) errs[key] = issue.message;
      }
      setProfileErrors(errs);
      return;
    }
    setProfileErrors({});
    setSaving(true);
    try {
      const updated = await updateProfile(parsed.data);
      updateUser({ fullName: updated.fullName, phone: updated.phone });
      setPhone(updated.phone);
      toast.success("Profile updated.");
    } catch {
      toast.error("We couldn't save your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const savePassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = passwordSchema.safeParse({ current, next, confirm });
    if (!parsed.success) {
      const errs: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as string;
        if (key && !errs[key]) errs[key] = issue.message;
      }
      setPasswordErrors(errs);
      return;
    }
    setPasswordErrors({});
    setChanging(true);
    try {
      await changePassword(parsed.data.current, parsed.data.next);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed. Use it on your next sign-in.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "We couldn't change your password.");
    } finally {
      setChanging(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="My profile"
        description="Your account details and what your role lets you do."
      />

      <div className="fn-panel flex flex-wrap items-center gap-4 p-5">
        <Avatar className="size-14">
          <AvatarFallback className="bg-primary-soft text-primary">
            {initials(user?.fullName ?? "FN")}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="font-display text-xl font-semibold">{user?.fullName}</p>
          <p className="text-sm text-muted-foreground">
            {user ? ROLE_LABELS[user.role] : "—"}
            {session?.school ? ` · ${session.school.name}` : ""}
          </p>
        </div>
      </div>

      <form
        className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
        onSubmit={(e) => void saveProfile(e)}
        noValidate
      >
        <div className="space-y-2">
          <Label htmlFor="profile-name">Full name</Label>
          <Input
            id="profile-name"
            className="h-11"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            aria-invalid={Boolean(profileErrors["fullName"])}
          />
          {profileErrors["fullName"] ? <FieldError>{profileErrors["fullName"]}</FieldError> : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="profile-phone">Phone number</Label>
          <Input
            id="profile-phone"
            className="h-11"
            inputMode="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            aria-invalid={Boolean(profileErrors["phone"])}
          />
          {profileErrors["phone"] ? <FieldError>{profileErrors["phone"]}</FieldError> : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="profile-email">Email address</Label>
          <Input
            id="profile-email"
            className="h-11"
            value={user?.email ?? ""}
            readOnly
            aria-describedby="email-hint"
          />
          <p id="email-hint" className="text-sm text-muted-foreground">
            Ask your school administrator to change your sign-in email.
          </p>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </form>

      <form
        className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
        onSubmit={(e) => void savePassword(e)}
        noValidate
      >
        <h2 className="font-medium sm:col-span-2">Change password</h2>
        <div className="space-y-2">
          <Label htmlFor="pw-current">Current password</Label>
          <Input
            id="pw-current"
            type="password"
            autoComplete="current-password"
            className="h-11"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            aria-invalid={Boolean(passwordErrors["current"])}
          />
          {passwordErrors["current"] ? <FieldError>{passwordErrors["current"]}</FieldError> : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="pw-next">New password</Label>
          <Input
            id="pw-next"
            type="password"
            autoComplete="new-password"
            className="h-11"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            aria-describedby="pw-next-hint"
            aria-invalid={Boolean(passwordErrors["next"])}
          />
          <p id="pw-next-hint" className="text-sm text-muted-foreground">
            At least 8 characters, with a letter and a number.
          </p>
          {passwordErrors["next"] ? <FieldError>{passwordErrors["next"]}</FieldError> : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="pw-confirm">Repeat new password</Label>
          <Input
            id="pw-confirm"
            type="password"
            autoComplete="new-password"
            className="h-11"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={Boolean(passwordErrors["confirm"])}
          />
          {passwordErrors["confirm"] ? <FieldError>{passwordErrors["confirm"]}</FieldError> : null}
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" variant="outline" disabled={changing}>
            {changing ? "Changing…" : "Change password"}
          </Button>
        </div>
      </form>

      <section className="fn-panel space-y-3 p-5">
        <h2 className="font-medium">Your permissions</h2>
        <p className="text-sm text-muted-foreground">
          These control what you can see and do. Only a school administrator can change them.
        </p>
        <ul className="flex flex-wrap gap-2">
          {(user?.permissions ?? []).map((permission) => (
            <li key={permission}>
              <Badge variant="outline">{titleCase(permission.replace(".", " · "))}</Badge>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
