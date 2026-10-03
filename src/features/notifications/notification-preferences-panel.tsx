import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { notificationMeta } from "@/features/notifications/notification-model";
import {
  getNotificationPreferences,
  saveNotificationPreferences,
} from "@/services/school.service";
import type { NotificationPreference } from "@/types";

/**
 * Per-account notification preferences.
 *
 * These are preferences about *this person's* inbox, not about the school, so
 * the endpoint is self-service and this panel is reachable by every role rather
 * than sitting behind a school-management permission. It appears both in
 * Settings for staff and on the notifications page for parents and students,
 * who have no Settings screen of their own.
 *
 * Turning a type off stops new notifications of that type from being written.
 * It deliberately does not delete anything already delivered: unsent is not the
 * same as unread, and quietly emptying somebody's history would be a worse
 * surprise than leaving a notice they can still open.
 */

/** What each toggle means for the person reading it. */
const DESCRIPTIONS: Record<NotificationPreference["type"], string> = {
  payment: "Payments recorded, verified or reversed against your account.",
  result: "Results released for you or a child linked to you.",
  attendance: "Register gaps that need attention, and absence information.",
  announcement: "Notices the school publishes to your audience.",
  subscription: "Renewal reminders for this school's plan.",
  security: "Sign-ins and password or account changes.",
  ai: "How much of the school's AI allowance has been used.",
  system: "Maintenance, downtime and other operational messages.",
};

export function NotificationPreferencesPanel({ compact = false }: { compact?: boolean }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: getNotificationPreferences,
  });
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState(false);

  // Seed the draft once the server has answered, and whenever the server's
  // answer changes, so a failed save visibly snaps back to the stored truth.
  useEffect(() => {
    if (!query.data) return;
    setDraft(Object.fromEntries(query.data.map((p) => [p.type, p.inApp])));
    setDirty(false);
  }, [query.data]);

  const save = useMutation({
    mutationFn: saveNotificationPreferences,
    onSuccess: (saved) => {
      setDraft(Object.fromEntries(saved.map((p) => [p.type, p.inApp])));
      setDirty(false);
      queryClient.setQueryData(["notification-preferences"], saved);
      toast.success("Notification preferences saved.");
    },
    onError: () => toast.error("We couldn't save your preferences. Please try again."),
  });

  if (query.isError) {
    return (
      <ErrorState
        onRetry={() => void query.refetch()}
        message="We couldn't load your notification preferences."
      />
    );
  }
  if (query.isPending) return <ListSkeleton rows={4} />;

  function toggle(type: NotificationPreference["type"], inApp: boolean) {
    setDraft((prev) => ({ ...prev, [type]: inApp }));
    setDirty(true);
  }

  return (
    <div className="fn-panel divide-y p-0">
      {query.data.map((pref) => (
        <div key={pref.type} className="flex items-center justify-between gap-4 p-5">
          <div className="min-w-0">
            <Label htmlFor={`pref-${pref.type}`} className="font-medium">
              {pref.label || notificationMeta(pref.type).label}
            </Label>
            {!compact ? (
              <p className="text-sm text-muted-foreground">{DESCRIPTIONS[pref.type]}</p>
            ) : null}
          </div>
          <Switch
            id={`pref-${pref.type}`}
            checked={draft[pref.type] ?? pref.inApp}
            onCheckedChange={(checked) => toggle(pref.type, checked)}
          />
        </div>
      ))}
      {dirty ? (
        <div className="flex items-center justify-end gap-3 p-4">
          <Button
            variant="ghost"
            onClick={() => {
              setDraft(Object.fromEntries((query.data ?? []).map((p) => [p.type, p.inApp])));
              setDirty(false);
            }}
          >
            Discard
          </Button>
          <Button
            onClick={() =>
              save.mutate(
                Object.keys(draft).map((type) => ({
                  type: type as NotificationPreference["type"],
                  inApp: draft[type] ?? true,
                })),
              )
            }
            disabled={save.isPending}
          >
            {save.isPending ? "Saving…" : "Save preferences"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
