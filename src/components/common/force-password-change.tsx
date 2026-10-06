import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSession } from "@/auth/session";
import { changePassword } from "@/services/auth.service";

const schema = z
  .object({
    current: z.string().min(1, { message: "Enter your current password" }),
    next: z
      .string()
      .min(8, { message: "Use at least 8 characters" })
      .max(72, { message: "Password is too long" }),
    confirm: z.string().min(1, { message: "Repeat your new password" }),
  })
  .refine((v) => v.next === v.confirm, {
    message: "The two passwords do not match.",
    path: ["confirm"],
  });

export function ForcePasswordChangeDialog() {
  const { session, updateUser } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const required = session?.user?.mustChangePassword === true;
  if (!session) return null;

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = schema.safeParse({ current, next, confirm });
    if (!parsed.success) {
      const errs: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as string;
        if (key && !errs[key]) errs[key] = issue.message;
      }
      setErrors(errs);
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      await changePassword(parsed.data.current, parsed.data.next);
      updateUser({ mustChangePassword: false });
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password updated. Welcome back!");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "We couldn't change your password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={required}>
      <DialogContent
        className="sm:max-w-md [&>button]:hidden"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Set your new password</DialogTitle>
          <DialogDescription>
            You are signed in with a temporary password. Choose a new password to continue.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="force-current">Current password</Label>
            <Input
              id="force-current"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
            {errors["current"] ? <p className="text-sm text-destructive">{errors["current"]}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="force-next">New password</Label>
            <Input
              id="force-next"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
            {errors["next"] ? <p className="text-sm text-destructive">{errors["next"]}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="force-confirm">Confirm new password</Label>
            <Input
              id="force-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {errors["confirm"] ? <p className="text-sm text-destructive">{errors["confirm"]}</p> : null}
          </div>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saving…" : "Update password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
