import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { dateTimeFmt } from "@/lib/format";
import { getPlatformSettings, updatePlatformSettings } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/settings")({
  head: () => ({
    meta: [
      { title: "Platform Settings — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Trial windows, billing cycles, grace periods and support controls.",
      },
      { property: "og:title", content: "Platform Settings — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSettingsPage,
});

function PlatformSettingsPage() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["platform", "settings"], queryFn: getPlatformSettings });
  const [form, setForm] = useState({
    trialDays: "7",
    subscriptionPeriodDays: "30",
    gracePeriodDays: "0",
    supportEmail: "",
    maintenanceMessage: "",
  });
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (query.data && !hydrated) {
      setForm({
        trialDays: String(query.data.trialDays),
        subscriptionPeriodDays: String(query.data.subscriptionPeriodDays),
        gracePeriodDays: String(query.data.gracePeriodDays),
        supportEmail: query.data.supportEmail ?? "",
        maintenanceMessage: query.data.maintenanceMessage ?? "",
      });
      setHydrated(true);
    }
  }, [query.data, hydrated]);

  const save = useMutation({
    mutationFn: () =>
      updatePlatformSettings({
        trialDays: Number(form.trialDays) || 0,
        subscriptionPeriodDays: Number(form.subscriptionPeriodDays) || 0,
        gracePeriodDays: Number(form.gracePeriodDays) || 0,
        supportEmail: form.supportEmail.trim(),
        maintenanceMessage: form.maintenanceMessage.trim(),
      }),
    onSuccess: () => {
      toast.success("Platform settings saved");
      setHydrated(false);
      void queryClient.invalidateQueries({ queryKey: ["platform", "settings"] });
    },
    onError: () => toast.error("We couldn't save those settings."),
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Platform Settings"
          description="Trial windows, billing cycles and grace periods. Every change is audited with before/after values."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton rows={5} />
        ) : (
          <form
            className="fn-panel max-w-2xl space-y-4 p-5"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="ps-trial">Trial days</Label>
                <Input
                  id="ps-trial"
                  className="h-11"
                  inputMode="numeric"
                  value={form.trialDays}
                  onChange={(e) => set("trialDays")(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ps-period">Billing cycle (days)</Label>
                <Input
                  id="ps-period"
                  className="h-11"
                  inputMode="numeric"
                  value={form.subscriptionPeriodDays}
                  onChange={(e) => set("subscriptionPeriodDays")(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ps-grace">Grace period (days)</Label>
                <Input
                  id="ps-grace"
                  className="h-11"
                  inputMode="numeric"
                  value={form.gracePeriodDays}
                  onChange={(e) => set("gracePeriodDays")(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ps-support">Support email</Label>
              <Input
                id="ps-support"
                className="h-11"
                type="email"
                value={form.supportEmail}
                onChange={(e) => set("supportEmail")(e.target.value)}
                placeholder="support@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ps-maintenance">Maintenance message</Label>
              <Textarea
                id="ps-maintenance"
                rows={3}
                value={form.maintenanceMessage}
                onChange={(e) => set("maintenanceMessage")(e.target.value)}
                placeholder="Shown to schools during planned downtime"
              />
            </div>
            {query.data?.updatedAt ? (
              <p className="text-xs text-muted-foreground">
                Last updated {dateTimeFmt(query.data.updatedAt)}
              </p>
            ) : null}
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save settings"}
            </Button>
          </form>
        )}

        <section className="max-w-2xl space-y-2">
          <h2 className="font-medium">Supported feature limits</h2>
          <p className="text-sm text-muted-foreground">
            Per-plan user, storage, SMS, OTP and AI allowances are configured on each plan under{" "}
            <span className="font-medium">Subscription Plans</span>. This screen holds only the
            platform-wide commercial policy; plan-level limits stay with the plan so pricing and
            entitlement never drift apart.
          </p>
        </section>
      </div>
    </PermissionGate>
  );
}
