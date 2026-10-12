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
import { dateTimeFmt, naira } from "@/lib/format";
import { getPlatformSettings, updatePlatformSettings } from "@/services/platform.service";
import {
  getBillingPricing,
  getMessagingOverview,
  updateBillingPricing,
} from "@/services/platform.service";
import { StatCard } from "@/components/common/stat-card";

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

        <BillingPolicySection />
        <MessagingOverviewSection />
      </div>
    </PermissionGate>
  );
}

function BillingPolicySection() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["platform", "billing"], queryFn: getBillingPricing });
  const [form, setForm] = useState({
    studentPriceKobo: "11500",
    smsPriceKobo: "1000",
    graceDays: "3",
    autoRenew: true,
    smsEnabledGlobal: true,
    minDepositKobo: "10000",
  });
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (query.data && !hydrated) {
      setForm({
        studentPriceKobo: String(query.data.studentPriceKobo),
        smsPriceKobo: String(query.data.smsPriceKobo),
        graceDays: String(query.data.graceDays),
        autoRenew: query.data.autoRenew,
        smsEnabledGlobal: query.data.smsEnabledGlobal,
        minDepositKobo: String(query.data.minDepositKobo),
      });
      setHydrated(true);
    }
  }, [query.data, hydrated]);

  const save = useMutation({
    mutationFn: () =>
      updateBillingPricing({
        studentPriceKobo: Number(form.studentPriceKobo) || 0,
        smsPriceKobo: Number(form.smsPriceKobo) || 0,
        graceDays: Number(form.graceDays) || 0,
        autoRenew: form.autoRenew,
        smsEnabledGlobal: form.smsEnabledGlobal,
        minDepositKobo: Number(form.minDepositKobo) || 0,
      }),
    onSuccess: () => {
      toast.success("Billing policy saved. Future charges use the new prices.");
      setHydrated(false);
      void queryClient.invalidateQueries({ queryKey: ["platform", "billing"] });
    },
    onError: () => toast.error("We couldn't save the billing policy."),
  });

  const setText =
    (key: "studentPriceKobo" | "smsPriceKobo" | "graceDays" | "minDepositKobo") =>
    (value: string) =>
      setForm((f) => ({ ...f, [key]: value }));

  return (
    <section className="max-w-2xl space-y-3">
      <h2 className="font-medium">Wallet billing policy</h2>
      <p className="text-sm text-muted-foreground">
        Prices are in kobo. Changes apply to future charges only — already-paid periods keep their
        price. Every change is audited.
      </p>
      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton rows={5} />
      ) : (
        <form
          className="fn-panel space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="bp-student">Student access (kobo / month)</Label>
              <Input
                id="bp-student"
                className="h-11"
                inputMode="numeric"
                value={form.studentPriceKobo}
                onChange={(e) => setText("studentPriceKobo")(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bp-sms">SME alert (kobo each)</Label>
              <Input
                id="bp-sms"
                className="h-11"
                inputMode="numeric"
                value={form.smsPriceKobo}
                onChange={(e) => setText("smsPriceKobo")(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bp-grace">Grace period (days, 0–30)</Label>
              <Input
                id="bp-grace"
                className="h-11"
                inputMode="numeric"
                value={form.graceDays}
                onChange={(e) => setText("graceDays")(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bp-min">Minimum deposit (kobo)</Label>
              <Input
                id="bp-min"
                className="h-11"
                inputMode="numeric"
                value={form.minDepositKobo}
                onChange={(e) => setText("minDepositKobo")(e.target.value)}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.autoRenew}
              onChange={(e) => setForm((f) => ({ ...f, autoRenew: e.target.checked }))}
            />
            Automatic renewal while the wallet is funded
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.smsEnabledGlobal}
              onChange={(e) => setForm((f) => ({ ...f, smsEnabledGlobal: e.target.checked }))}
            />
            SME alerts enabled platform-wide (unchecking blocks every school)
          </label>
          {query.data?.priceChangedAt ? (
            <p className="text-xs text-muted-foreground">
              Last changed {dateTimeFmt(query.data.priceChangedAt)}
            </p>
          ) : null}
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save billing policy"}
          </Button>
        </form>
      )}
    </section>
  );
}

function MessagingOverviewSection() {
  const query = useQuery({
    queryKey: ["platform", "messaging"],
    queryFn: getMessagingOverview,
  });
  return (
    <section className="max-w-2xl space-y-3">
      <h2 className="font-medium">SME alerts overview</h2>
      <p className="text-sm text-muted-foreground">
        Customer charges versus known provider costs. Messages whose provider cost is unknown are
        counted separately — never assumed free.
      </p>
      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton rows={3} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <StatCard label="Alerts sent" value={String(query.data.alerts.sent)} tone="success" />
          <StatCard
            label="Alerts failed"
            value={String(query.data.alerts.failed)}
            tone={query.data.alerts.failed ? "danger" : "success"}
          />
          <StatCard
            label="Customer charges"
            value={naira(query.data.alerts.chargedKobo / 100)}
            tone="success"
          />
          <StatCard
            label="Unknown provider cost"
            value={String(query.data.alerts.unknownCostCount)}
            hint={`Known cost ${naira(query.data.alerts.knownCostKobo / 100)}`}
            tone={query.data.alerts.unknownCostCount ? "warning" : "success"}
          />
        </div>
      )}
    </section>
  );
}
