import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { naira } from "@/lib/format";
import {
  createPlatformPlan,
  listPlatformPlans,
  listPlatformSchools,
  updatePlatformPlan,
  type PlatformPlan,
} from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/plans")({
  head: () => ({
    meta: [
      { title: "Subscription Plans — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Create and price subscription plans for schools on Frontline Nexus.",
      },
      { property: "og:title", content: "Subscription Plans — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformPlansPage,
});

interface PlanForm {
  label: string;
  description: string;
  billingInterval: string;
  currency: string;
  trialDays: string;
  minStudents: string;
  maxStudents: string;
  monthlyPrice: string;
  sortOrder: string;
}

const EMPTY: PlanForm = {
  label: "",
  description: "",
  billingInterval: "monthly",
  currency: "NGN",
  trialDays: "7",
  minStudents: "1",
  maxStudents: "",
  monthlyPrice: "",
  sortOrder: "0",
};

function PlatformPlansPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<PlatformPlan | null>(null);
  const [creating, setCreating] = useState(false);

  const plans = useQuery({ queryKey: ["platform", "plans"], queryFn: listPlatformPlans });
  const schools = useQuery({
    queryKey: ["platform", "schools"],
    queryFn: () => listPlatformSchools(),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ plan, isActive }: { plan: PlatformPlan; isActive: boolean }) =>
      updatePlatformPlan(plan.id as string, { isActive }),
    onSuccess: (plan) => {
      toast.success(`${plan.label} ${plan.isActive ? "activated" : "deactivated"}`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "plans"] });
    },
    onError: () => toast.error("We couldn't update that plan."),
  });

  const list = plans.data ?? [];
  const schoolList = schools.data ?? [];
  const schoolsPerPlan = (plan: PlatformPlan) =>
    schoolList.filter((s) => s.tierId === plan.id).length;

  return (
    <PermissionGate permission="subscription.write">
      <div className="space-y-6">
        <PageHeader
          title="Subscription Plans"
          description="Price the catalogue for new subscribers. Existing schools keep the price they signed up at until you explicitly move them."
          actions={
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden="true" />
              New plan
            </Button>
          }
        />

        {plans.isError ? (
          <ErrorState onRetry={() => void plans.refetch()} />
        ) : plans.isPending ? (
          <ListSkeleton />
        ) : list.length === 0 ? (
          <EmptyState
            title="No plans yet"
            description="Create the first subscription plan to start billing schools."
          />
        ) : (
          <ul className="fn-panel divide-y">
            {list.map((plan) => {
              const price = Number(plan.monthlyPrice) || 0;
              const count = schoolsPerPlan(plan);
              return (
                <li key={String(plan.id)} className="flex flex-wrap items-center gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{plan.label}</p>
                    <p className="text-sm text-muted-foreground">
                      {naira(price)}/{plan.billingInterval ?? "monthly"} · {plan.minStudents}–
                      {plan.maxStudents ?? "∞"} students · {count} school
                      {count === 1 ? "" : "s"} · {plan.trialDays ?? 7}-day trial
                    </p>
                    {plan.description ? (
                      <p className="mt-0.5 text-sm text-muted-foreground">{plan.description}</p>
                    ) : null}
                  </div>
                  <StatusBadge status={plan.isActive === false ? "suspended" : "active"} />
                  <Button size="sm" variant="outline" onClick={() => setEditing(plan)}>
                    <Pencil className="size-3.5" aria-hidden="true" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={toggleMutation.isPending}
                    onClick={() =>
                      toggleMutation.mutate({ plan, isActive: plan.isActive === false })
                    }
                  >
                    {plan.isActive === false ? "Activate" : "Deactivate"}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}

        <p className="text-sm text-muted-foreground">
          Changing a plan&apos;s price applies to <strong>new subscribers only</strong>. To move an
          existing school to a new price, open Schools → Manage → Subscription and change the plan
          there with an explicit confirmation — the change is audited with before/after values.
        </p>

        <PlanDialog
          open={creating || editing !== null}
          plan={editing}
          onOpenChange={(open) => {
            if (!open) {
              setCreating(false);
              setEditing(null);
            }
          }}
        />
      </div>
    </PermissionGate>
  );
}

function PlanDialog({
  open,
  plan,
  onOpenChange,
}: {
  open: boolean;
  plan: PlatformPlan | null;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanForm>(EMPTY);
  const [wasOpen, setWasOpen] = useState(false);

  if (open && !wasOpen) {
    setWasOpen(true);
    setForm({
      ...EMPTY,
      label: String(plan?.label ?? ""),
      description: String(plan?.description ?? ""),
      billingInterval: String(plan?.billingInterval ?? "monthly"),
      currency: String(plan?.currency ?? "NGN"),
      trialDays: String(plan?.trialDays ?? "7"),
      minStudents: String(plan?.minStudents ?? "1"),
      maxStudents: plan?.maxStudents == null ? "" : String(plan.maxStudents),
      monthlyPrice: plan ? String(plan.monthlyPrice) : "",
      sortOrder: String(plan?.sortOrder ?? "0"),
    });
  }
  if (!open && wasOpen) setWasOpen(false);

  const save = useMutation({
    mutationFn: () => {
      const payload: Partial<PlatformPlan> = {
        label: form.label.trim(),
        description: form.description.trim(),
        billingInterval: form.billingInterval,
        currency: form.currency.trim() || "NGN",
        trialDays: Number(form.trialDays) || 0,
        minStudents: Number(form.minStudents) || 0,
        maxStudents: form.maxStudents === "" ? null : Number(form.maxStudents),
        monthlyPrice: form.monthlyPrice === "" ? 0 : Number(form.monthlyPrice),
        sortOrder: Number(form.sortOrder) || 0,
      };
      return plan?.id != null ? updatePlatformPlan(plan.id, payload) : createPlatformPlan(payload);
    },
    onSuccess: (saved) => {
      toast.success(`${saved.label} saved`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "plans"] });
      onOpenChange(false);
    },
    onError: () => toast.error("We couldn't save that plan. Check the details and try again."),
  });

  const set = (key: keyof PlanForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-lg">
            {plan ? `Edit ${plan.label}` : "New subscription plan"}
          </DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.label.trim()) {
              toast.error("Give the plan a name.");
              return;
            }
            save.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="plan-label">Name</Label>
            <Input
              id="plan-label"
              className="h-11"
              required
              value={form.label}
              onChange={(e) => set("label")(e.target.value)}
              placeholder="e.g. 201 – 400 students"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="plan-desc">Description</Label>
            <Textarea
              id="plan-desc"
              rows={2}
              value={form.description}
              onChange={(e) => set("description")(e.target.value)}
              placeholder="Who this plan is for"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="plan-price">Price</Label>
              <Input
                id="plan-price"
                className="h-11"
                inputMode="decimal"
                required
                value={form.monthlyPrice}
                onChange={(e) => set("monthlyPrice")(e.target.value)}
                placeholder="19000"
              />
            </div>
            <div className="space-y-2">
              <Label>Currency</Label>
              <Input
                className="h-11"
                value={form.currency}
                onChange={(e) => set("currency")(e.target.value.toUpperCase())}
                maxLength={8}
              />
            </div>
            <div className="space-y-2">
              <Label>Billing interval</Label>
              <Select value={form.billingInterval} onValueChange={set("billingInterval")}>
                <SelectTrigger className="h-11">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="termly">Termly</SelectItem>
                  <SelectItem value="yearly">Yearly</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="plan-min">Min students</Label>
              <Input
                id="plan-min"
                className="h-11"
                inputMode="numeric"
                value={form.minStudents}
                onChange={(e) => set("minStudents")(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="plan-max">Max students (blank = none)</Label>
              <Input
                id="plan-max"
                className="h-11"
                inputMode="numeric"
                value={form.maxStudents}
                onChange={(e) => set("maxStudents")(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="plan-trial">Trial days</Label>
              <Input
                id="plan-trial"
                className="h-11"
                inputMode="numeric"
                value={form.trialDays}
                onChange={(e) => set("trialDays")(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="plan-order">Display order</Label>
            <Input
              id="plan-order"
              className="h-11"
              inputMode="numeric"
              value={form.sortOrder}
              onChange={(e) => set("sortOrder")(e.target.value)}
            />
          </div>
          {plan ? (
            <p className="rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm">
              This edits the catalogue for <strong>new</strong> subscribers. Schools already on this
              plan keep their current price until you move them individually.
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={save.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : plan ? "Save changes" : "Create plan"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
