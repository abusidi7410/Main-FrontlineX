import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Building2, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { useDebounced } from "@/hooks/use-debounced";
import { dateFmt, naira, numberFmt } from "@/lib/format";
import { tierById, SUBSCRIPTION_TIERS } from "@/constants/plans";
import { NIGERIAN_STATES, lgasForState } from "@/constants/nigeria";
import type { PlatformSchool } from "@/types";
import {
  createManualAdjustment,
  createPlatformSchool,
  deletePlatformSchool,
  getPlatformSchool,
  getSchoolMessaging,
  grantComplimentaryAccess,
  listPlatformPlans,
  listPlatformSchools,
  setSchoolStatus,
  updatePlatformSchool,
  updateSchoolMessaging,
  updateSchoolSubscription,
  type PlatformSchoolDetail,
  type RegisterSchoolResponse,
} from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/schools")({
  head: () => ({
    meta: [
      { title: "Schools — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Every school on Frontline Nexus with plan, size and account status.",
      },
      { property: "og:title", content: "Schools — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Every school on Frontline Nexus with plan, size and account status.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSchoolsPage,
});

const STATUSES = ["active", "trial", "grace", "pending_payment", "suspended"] as const;
const SCHOOL_TYPES = [
  { value: "nursery", label: "Nursery" },
  { value: "primary", label: "Primary" },
  { value: "secondary", label: "Secondary" },
  { value: "mixed", label: "Mixed" },
] as const;

const EMPTY_FORM = {
  name: "",
  schoolType: "mixed",
  state: "",
  lga: "",
  address: "",
  phone: "",
  email: "",
  website: "",
  tierId: "t100",
  currentSession: "2026/2027",
  currentTerm: "First Term",
};

function PlatformSchoolsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [manageId, setManageId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlatformSchool | null>(null);
  const debounced = useDebounced(search, 300);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["platform", "schools", debounced, status],
    queryFn: () => listPlatformSchools(debounced, status === "all" ? "" : status),
  });

  const mutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: (typeof STATUSES)[number] }) =>
      setSchoolStatus(id, next),
    onSuccess: (school) => {
      toast.success(`${school.name} is now ${school.status.replace("_", " ")}`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    },
    onError: () => toast.error("We couldn't update that school. Please try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ id, confirm }: { id: string; confirm: string }) =>
      deletePlatformSchool(id, confirm),
    onSuccess: (result) => {
      toast.success(`${result.deleted} was permanently deleted.`);
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "dashboard"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "We couldn't delete that school.");
    },
  });

  const schools = query.data ?? [];

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Schools"
          description="Search, register and manage every school on the platform."
          actions={
            <Button onClick={() => setRegisterOpen(true)}>
              <Building2 className="size-4" aria-hidden="true" />
              Register school
            </Button>
          }
        />

        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            className="h-11"
            placeholder="Search by school name or state"
            aria-label="Search schools"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-11 sm:w-56" aria-label="Filter by status">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s.replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : schools.length === 0 ? (
          <EmptyState
            title="No schools match your filters"
            description="Try another name, state or status, or register a new school."
          />
        ) : (
          <ul className="fn-panel divide-y">
            {schools.map((school) => (
              <li key={school.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{school.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {school.state} · {numberFmt(school.students)} students ·{" "}
                    {tierById(school.tierId).label} · joined {dateFmt(school.createdAt)}
                  </p>
                </div>
                <span className="tabular-nums text-sm text-muted-foreground">
                  {naira(school.mrr)}/mo
                </span>
                <StatusBadge status={school.status} />
                <Button size="sm" variant="outline" onClick={() => setManageId(school.id)}>
                  <Pencil className="size-3.5" aria-hidden="true" />
                  Manage
                </Button>
                {school.status !== "suspended" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate({ id: school.id, next: "suspended" })}
                  >
                    Suspend
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate({ id: school.id, next: "active" })}
                  >
                    Reactivate
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  disabled={deleteMutation.isPending}
                  onClick={() => setDeleteTarget(school)}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}

        <RegisterSchoolDialog open={registerOpen} onOpenChange={setRegisterOpen} />
        <ManageSchoolDialog
          schoolId={manageId}
          open={manageId !== null}
          onOpenChange={(open) => {
            if (!open) setManageId(null);
          }}
        />
        <DeleteSchoolDialog
          school={deleteTarget}
          isPending={deleteMutation.isPending}
          onOpenChange={(open) => {
            if (!open && !deleteMutation.isPending) setDeleteTarget(null);
          }}
          onConfirm={(id, confirm) => deleteMutation.mutate({ id, confirm })}
        />
      </div>
    </PermissionGate>
  );
}

function RegisterSchoolDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [created, setCreated] = useState<RegisterSchoolResponse | null>(null);

  useEffect(() => {
    if (open) {
      setForm(EMPTY_FORM);
      setCreated(null);
    }
  }, [open]);

  const createMutation = useMutation({
    mutationFn: createPlatformSchool,
    onSuccess: (school) => {
      setCreated(school);
      toast.success(`${school.name} registered and activated`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    },
    onError: async (err) => {
      const message =
        err instanceof Error && "fieldErrors" in err
          ? Object.values(
              (err as unknown as { fieldErrors: Record<string, string> }).fieldErrors,
            ).join(" ")
          : "We couldn't register the school. Please check the details.";
      toast.error(message);
    },
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const lgaOptions = lgasForState(form.state);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    createMutation.mutate(form);
  };

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch {
      toast.error("Couldn't copy. Select the text and copy manually.");
    }
  };

  const closeCreated = () => {
    setCreated(null);
    setForm(EMPTY_FORM);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? undefined : closeCreated())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-lg">
            {created ? "School registered" : "Register a school"}
          </DialogTitle>
        </DialogHeader>
        {created ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              A default admin account was created. Share these credentials with the school admin —
              the password must be changed after their first login.
            </p>
            {created.defaultCredentials ? (
              <div className="space-y-3 rounded-lg border p-4">
                <FieldRow
                  label="Admin email"
                  value={created.defaultCredentials.email}
                  onCopy={() =>
                    void copyText(created.defaultCredentials?.email ?? "", "Admin email")
                  }
                />
                <FieldRow
                  label="Default password"
                  value={created.defaultCredentials.password}
                  onCopy={() =>
                    void copyText(created.defaultCredentials?.password ?? "", "Default password")
                  }
                />
                <p className="text-xs text-muted-foreground">
                  The admin can change this password any time from account settings after logging
                  in.
                </p>
              </div>
            ) : null}
            <DialogFooter>
              <Button onClick={closeCreated} className="w-full">
                Done
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="reg-name">School name</Label>
              <Input
                id="reg-name"
                className="h-11"
                required
                placeholder="e.g. Sunrise Academy"
                value={form.name}
                onChange={(e) => set("name")(e.target.value)}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>School type</Label>
                <Select value={form.schoolType} onValueChange={set("schoolType")}>
                  <SelectTrigger className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SCHOOL_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-tier">Plan</Label>
                <Select value={form.tierId} onValueChange={set("tierId")}>
                  <SelectTrigger className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUBSCRIPTION_TIERS.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="reg-state">State</Label>
                <Select
                  value={form.state}
                  onValueChange={(value) => {
                    set("state")(value);
                    set("lga")("");
                  }}
                >
                  <SelectTrigger id="reg-state" className="h-11">
                    <SelectValue placeholder="Select state" />
                  </SelectTrigger>
                  <SelectContent>
                    {NIGERIAN_STATES.map((state) => (
                      <SelectItem key={state} value={state}>
                        {state}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-lga">LGA</Label>
                <Select value={form.lga} onValueChange={set("lga")} disabled={!form.state}>
                  <SelectTrigger id="reg-lga" className="h-11">
                    <SelectValue placeholder={form.state ? "Select LGA" : "Select a state first"} />
                  </SelectTrigger>
                  <SelectContent>
                    {lgaOptions.map((lga) => (
                      <SelectItem key={lga} value={lga}>
                        {lga}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-address">Address</Label>
              <Input
                id="reg-address"
                className="h-11"
                required
                placeholder="Street address"
                value={form.address}
                onChange={(e) => set("address")(e.target.value)}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="reg-phone">Phone</Label>
                <Input
                  id="reg-phone"
                  className="h-11"
                  required
                  placeholder="+234..."
                  value={form.phone}
                  onChange={(e) => set("phone")(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-email">Contact email</Label>
                <Input
                  id="reg-email"
                  type="email"
                  className="h-11"
                  required
                  placeholder="info@school.edu.ng"
                  value={form.email}
                  onChange={(e) => set("email")(e.target.value)}
                />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="reg-session">Session</Label>
                <Input
                  id="reg-session"
                  className="h-11"
                  value={form.currentSession}
                  onChange={(e) => set("currentSession")(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-website">Website</Label>
                <Input
                  id="reg-website"
                  className="h-11"
                  placeholder="https://..."
                  value={form.website}
                  onChange={(e) => set("website")(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={createMutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Registering…" : "Register school"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function FieldRow({ label, value, onCopy }: { label: string; value: string; onCopy: () => void }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label>{label}</Label>
        <Button type="button" variant="ghost" size="sm" onClick={onCopy}>
          Copy
        </Button>
      </div>
      <div className="rounded-md border bg-muted/50 px-3 py-2 font-mono text-sm">{value}</div>
    </div>
  );
}

type EditableSchool = {
  name: string;
  schoolType: string;
  state: string;
  lga: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  primaryColor: string;
  secondaryColor: string;
  currentSession: string;
  currentTerm: string;
};

function DeleteSchoolDialog({
  school,
  isPending,
  onOpenChange,
  onConfirm,
}: {
  school: PlatformSchool | null;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (id: string, confirm: string) => void;
}) {
  const [confirmName, setConfirmName] = useState("");

  useEffect(() => {
    if (!school) setConfirmName("");
  }, [school]);

  const matches = school !== null && confirmName.trim() === school.name;
  const canDelete = matches && !isPending;

  return (
    <Dialog
      open={school !== null}
      onOpenChange={(open) => {
        if (open && school) return;
        onOpenChange(open);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg">Delete {school?.name ?? "this school"}?</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This permanently deletes the school, its login accounts, students, staff, attendance,
            invoices and payments. This can't be undone.
          </p>
          <div className="space-y-2">
            <Label htmlFor="del-confirm">
              Type <span className="font-mono font-medium">{school?.name ?? "…"}</span> to confirm
            </Label>
            <Input
              id="del-confirm"
              className="h-11"
              autoFocus
              placeholder={school?.name ?? ""}
              value={confirmName}
              onChange={(event) => setConfirmName(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
              Cancel
            </Button>
            <Button
              disabled={!canDelete}
              variant="destructive"
              onClick={() => school && onConfirm(school.id, confirmName.trim())}
            >
              {isPending ? "Deleting…" : "Delete school permanently"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ManageSchoolDialog({
  schoolId,
  open,
  onOpenChange,
}: {
  schoolId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["platform", "school", schoolId],
    queryFn: () => getPlatformSchool(schoolId as string),
    enabled: open && schoolId !== null,
  });

  const [form, setForm] = useState<EditableSchool | null>(null);

  const school = detail.data;

  useEffect(() => {
    if (school) {
      setForm({
        name: school.name,
        schoolType: school.schoolType,
        state: school.state,
        lga: school.lga,
        address: school.address,
        phone: school.phone,
        email: school.email,
        website: school.website,
        primaryColor: school.primaryColor,
        secondaryColor: school.secondaryColor,
        currentSession: school.currentSession,
        currentTerm: school.currentTerm,
      });
    }
  }, [school]);

  const saveMutation = useMutation({
    mutationFn: ({ id, input }: { id: string; input: EditableSchool }) =>
      updatePlatformSchool(id, input),
    onSuccess: (updated) => {
      toast.success(`${updated.name} updated`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] });
    },
    onError: () => toast.error("We couldn't save those changes."),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: "active" | "suspended" }) =>
      setSchoolStatus(id, next),
    onSuccess: (updated) => {
      toast.success(`${updated.name} is now ${updated.status.replace("_", " ")}`);
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] });
    },
    onError: () => toast.error("We couldn't update that school."),
  });

  const set = (key: keyof EditableSchool) => (value: string) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const lgaOptions = lgasForState(form?.state ?? "");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!schoolId || !form) return;
    saveMutation.mutate({ id: schoolId, input: form });
  };

  useEffect(() => {
    if (!open) setForm(null);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-lg">Manage school</DialogTitle>
        </DialogHeader>

        {detail.isError ? (
          <ErrorState onRetry={() => void detail.refetch()} />
        ) : !school || !form ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <p className="font-medium">{school.name}</p>
              <StatusBadge status={school.status} />
              <span className="text-sm text-muted-foreground">
                {numberFmt(school.students)} students · {numberFmt(school.staffCount)} staff ·{" "}
                {naira(school.mrr)}/mo
              </span>
            </div>

            <SubscriptionControls school={school} schoolId={schoolId as string} />

            <ComplimentaryControls schoolId={schoolId as string} />

            <MessagingControls schoolId={schoolId as string} schoolName={school.name} />

            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="mng-name">School name</Label>
                <Input
                  id="mng-name"
                  className="h-11"
                  value={form.name}
                  onChange={(e) => set("name")(e.target.value)}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>School type</Label>
                  <Select value={form.schoolType} onValueChange={set("schoolType")}>
                    <SelectTrigger className="h-11">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SCHOOL_TYPES.map((t) => (
                        <SelectItem key={t.value} value={t.value}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mng-phone">Phone</Label>
                  <Input
                    id="mng-phone"
                    className="h-11"
                    value={form.phone}
                    onChange={(e) => set("phone")(e.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mng-state">State</Label>
                  <Select
                    value={form.state}
                    onValueChange={(value) => {
                      set("state")(value);
                      set("lga")("");
                    }}
                  >
                    <SelectTrigger id="mng-state" className="h-11">
                      <SelectValue placeholder="Select state" />
                    </SelectTrigger>
                    <SelectContent>
                      {NIGERIAN_STATES.map((state) => (
                        <SelectItem key={state} value={state}>
                          {state}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mng-lga">LGA</Label>
                  <Select value={form.lga} onValueChange={set("lga")} disabled={!form.state}>
                    <SelectTrigger id="mng-lga" className="h-11">
                      <SelectValue
                        placeholder={form.state ? "Select LGA" : "Select a state first"}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {lgaOptions.map((lga) => (
                        <SelectItem key={lga} value={lga}>
                          {lga}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mng-address">Address</Label>
                <Input
                  id="mng-address"
                  className="h-11"
                  value={form.address}
                  onChange={(e) => set("address")(e.target.value)}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mng-email">Contact email</Label>
                  <Input
                    id="mng-email"
                    className="h-11"
                    value={form.email}
                    onChange={(e) => set("email")(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mng-website">Website</Label>
                  <Input
                    id="mng-website"
                    className="h-11"
                    value={form.website}
                    onChange={(e) => set("website")(e.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mng-session">Session</Label>
                  <Input
                    id="mng-session"
                    className="h-11"
                    value={form.currentSession}
                    onChange={(e) => set("currentSession")(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mng-term">Term</Label>
                  <Input
                    id="mng-term"
                    className="h-11"
                    value={form.currentTerm}
                    onChange={(e) => set("currentTerm")(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter className="sm:justify-between">
                <Button
                  type="button"
                  variant="outline"
                  disabled={statusMutation.isPending}
                  onClick={() =>
                    schoolId &&
                    statusMutation.mutate({
                      id: schoolId,
                      next: school.status === "suspended" ? "active" : "suspended",
                    })
                  }
                >
                  {school.status === "suspended" ? "Reactivate" : "Suspend"}
                </Button>
                <Button type="submit" disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? "Saving…" : "Save changes"}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Subscription lifecycle + complimentary access for one school.
 *
 * Lives inside the school's Manage dialog (not as its own sidebar entry):
 * plan changes, extensions, suspensions and complimentary grants all act on
 * this school's subscription and every one is audited with before/after
 * values. Complimentary access records who/when/reason and never writes a
 * payment row.
 */
function SubscriptionControls({
  school,
  schoolId,
}: {
  school: PlatformSchoolDetail;
  schoolId: string;
}) {
  const queryClient = useQueryClient();
  const [planId, setPlanId] = useState("");
  const [extendDays, setExtendDays] = useState("30");
  const [grantUntil, setGrantUntil] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);

  const plans = useQuery({ queryKey: ["platform", "plans"], queryFn: listPlatformPlans });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    void queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] });
  };

  const mutation = useMutation({
    mutationFn: (input: Parameters<typeof updateSchoolSubscription>[1]) =>
      updateSchoolSubscription(schoolId, input),
    onSuccess: (updated) => {
      toast.success(`${updated.name} subscription updated`);
      setConfirming(null);
      setReason("");
      refresh();
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "We couldn't update that subscription."),
  });

  const needReason = (action: string) => {
    if (!reason.trim()) {
      toast.error(`Add a reason — it is required to ${action} and is kept in the audit log.`);
      return false;
    }
    return true;
  };

  const planOptions = (plans.data ?? []).map((p) => ({
    value: String(p.id ?? p.label),
    label: `${p.label} — ${naira(Number(p.monthlyPrice) || 0)}`,
  }));

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-muted/30 p-4">
      <div>
        <h3 className="font-medium">Subscription</h3>
        <p className="text-sm text-muted-foreground">
          {school.planName || "No plan"} ·{" "}
          {school.expiresAt
            ? `expires ${new Date(school.expiresAt).toLocaleDateString()}`
            : "no expiry set"}
          {school.overrideActive ? (
            <>
              {" "}
              ·{" "}
              <span className="font-medium text-warning">
                complimentary until{" "}
                {school.overrideUntil
                  ? new Date(school.overrideUntil).toLocaleDateString()
                  : "revoked"}
              </span>
            </>
          ) : null}
        </p>
        {school.overrideActive ? (
          <p className="mt-1 text-xs text-muted-foreground">
            Granted{school.overrideBy ? ` by ${school.overrideBy}` : ""}
            {school.overrideAt ? ` on ${new Date(school.overrideAt).toLocaleDateString()}` : ""}.
            Reason: {school.overrideReason || school.overrideNote || "—"}
          </p>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Change plan</Label>
          <div className="flex gap-2">
            <Select value={planId} onValueChange={setPlanId}>
              <SelectTrigger className="h-10" aria-label="Select plan">
                <SelectValue placeholder="Select plan" />
              </SelectTrigger>
              <SelectContent>
                {planOptions.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              className="h-10 shrink-0"
              disabled={!planId || mutation.isPending}
              onClick={() => setConfirming("plan")}
            >
              Apply
            </Button>
          </div>
          {confirming === "plan" ? (
            <div className="space-y-2 rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
              <p>
                Move {school.name} to the selected plan now? The new price applies to this school
                from its next cycle; other schools are unaffected.
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={mutation.isPending}
                  onClick={() => mutation.mutate({ planId, reason: reason.trim() || undefined })}
                >
                  Confirm move
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="sub-extend">Extend access (days)</Label>
          <div className="flex gap-2">
            <Input
              id="sub-extend"
              className="h-10"
              inputMode="numeric"
              value={extendDays}
              onChange={(e) => setExtendDays(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-10 shrink-0"
              disabled={mutation.isPending}
              onClick={() => {
                const days = Number(extendDays);
                if (!days || days <= 0) {
                  toast.error("Enter a positive number of days.");
                  return;
                }
                mutation.mutate({ extendDays: days, reason: reason.trim() || undefined });
              }}
            >
              Extend
            </Button>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="sub-reason">Reason (required for grants, revocations, suspensions)</Label>
        <Input
          id="sub-reason"
          className="h-10"
          placeholder="e.g. Partnership pilot — Q4, approved by ops"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sub-grant-until">Complimentary until (blank = until revoked)</Label>
          <Input
            id="sub-grant-until"
            type="date"
            className="h-10"
            value={grantUntil}
            onChange={(e) => setGrantUntil(e.target.value)}
          />
          <div className="flex gap-2">
            {!school.overrideActive ? (
              <Button
                size="sm"
                disabled={mutation.isPending}
                onClick={() => {
                  if (!needReason("grant complimentary access")) return;
                  mutation.mutate({
                    overrideActive: true,
                    overrideUntil: grantUntil || null,
                    reason: reason.trim(),
                    note: reason.trim().slice(0, 200),
                  });
                }}
              >
                Grant complimentary access
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => {
                  if (!needReason("revoke complimentary access")) return;
                  mutation.mutate({ overrideActive: false, reason: reason.trim() });
                }}
              >
                Revoke complimentary access
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            No payment is recorded for complimentary access — the entitlement is stored separately
            from verified payments.
          </p>
        </div>

        <div className="space-y-2">
          <Label>Suspension</Label>
          <div className="flex gap-2">
            {school.status !== "suspended" ? (
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:text-destructive"
                disabled={mutation.isPending}
                onClick={() => {
                  if (!needReason("suspend this school")) return;
                  mutation.mutate({ status: "suspended", reason: reason.trim() });
                }}
              >
                Suspend school
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => {
                  if (!needReason("restore this school")) return;
                  mutation.mutate({ status: "active", reason: reason.trim() });
                }}
              >
                Restore access
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Suspension locks every login for this school; data is preserved and restored on
            reactivation.
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * Per-student complimentary access (wallet model): a free one-month
 * entitlement with a written reason. No wallet movement, no fake payment —
 * the grant, reason and granter are recorded and audited.
 */
function ComplimentaryControls({ schoolId }: { schoolId: string }) {
  const [studentId, setStudentId] = useState("");
  const [reason, setReason] = useState("");

  const grant = useMutation({
    mutationFn: () =>
      grantComplimentaryAccess({
        schoolId,
        studentId: studentId.trim(),
        reason: reason.trim(),
      }),
    onSuccess: (result) => {
      toast.success(
        result.created
          ? `Complimentary access granted through ${result.periodEnd}.`
          : "That student already has active access — no grant made.",
      );
      setStudentId("");
      setReason("");
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Complimentary grant failed."),
  });

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-muted/30 p-4">
      <div>
        <h3 className="font-medium">Complimentary student access</h3>
        <p className="text-sm text-muted-foreground">
          Free one-month access for one student. Needs the student&apos;s ID from the school
          roster and a written reason — both kept in the audit log.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="comp-student">Student ID</Label>
          <Input
            id="comp-student"
            className="h-10"
            placeholder="Student public ID"
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="comp-reason">Reason (required)</Label>
          <Input
            id="comp-reason"
            className="h-10"
            placeholder="e.g. Flood relief — September intake"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </div>
      <Button
        size="sm"
        disabled={!studentId.trim() || !reason.trim() || grant.isPending}
        onClick={() => grant.mutate()}
      >
        {grant.isPending ? "Granting…" : "Grant complimentary access"}
      </Button>
    </section>
  );
}

/**
 * Wallet + SME alert controls for one school.
 *
 * Lives inside the school's Manage dialog: wallet balance and alert usage are
 * read-only facts, while blocking/unblocking alerts and manual adjustments are
 * platform-only actions — every one audited with before/after values.
 */
function MessagingControls({ schoolId, schoolName }: { schoolId: string; schoolName: string }) {
  const queryClient = useQueryClient();
  const [adjustNaira, setAdjustNaira] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [confirmAdjust, setConfirmAdjust] = useState(false);

  const query = useQuery({
    queryKey: ["platform", "school", schoolId, "messaging"],
    queryFn: () => getSchoolMessaging(schoolId),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: ["platform", "school", schoolId, "messaging"],
    });
  };

  const blockMutation = useMutation({
    mutationFn: (blocked: boolean) => updateSchoolMessaging(schoolId, { platformBlocked: blocked }),
    onSuccess: (updated) => {
      toast.success(
        updated.platformBlocked
          ? `${schoolName} is now blocked from SME alerts`
          : `${schoolName} can use SME alerts again`,
      );
      refresh();
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "We couldn't update messaging."),
  });

  const adjustMutation = useMutation({
    mutationFn: () =>
      createManualAdjustment({
        schoolId,
        amountKobo: Math.round(Number(adjustNaira) * 100),
        reason: adjustReason.trim(),
      }),
    onSuccess: (result) => {
      toast.success(`Wallet adjusted. New balance ${naira(result.balanceKobo / 100)}.`);
      setAdjustNaira("");
      setAdjustReason("");
      setConfirmAdjust(false);
      refresh();
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "We couldn't adjust the wallet."),
  });

  const data = query.data;

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-muted/30 p-4">
      <div>
        <h3 className="font-medium">Wallet & SME alerts</h3>
        {data ? (
          <p className="text-sm text-muted-foreground">
            Balance {naira(data.balanceKobo / 100)} · {data.usage.sent} alert(s) sent ·{" "}
            {naira(data.usage.chargedKobo / 100)} charged
            {data.platformBlocked ? (
              <>
                {" "}
                · <span className="font-medium text-destructive">blocked by platform</span>
              </>
            ) : data.schoolEnabled ? (
              " · school switch on"
            ) : (
              " · school switch off"
            )}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">Loading wallet and alert usage…</p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={!data || blockMutation.isPending}
          className={data?.platformBlocked ? undefined : "text-destructive hover:text-destructive"}
          onClick={() => blockMutation.mutate(!(data?.platformBlocked ?? false))}
        >
          {data?.platformBlocked ? "Unblock SME alerts" : "Block SME alerts"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Blocking stops new billable alerts even if the school switch is on. Messages already
        accepted by the provider are unaffected.
      </p>

      <div className="space-y-2 border-t border-border/60 pt-3">
        <Label>Manual wallet adjustment</Label>
        {confirmAdjust ? (
          <div className="space-y-2 rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
            <p>
              Adjust by {naira(Number(adjustNaira) || 0)}? A reason is required and the adjustment
              is written to the audit log with before/after values.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={adjustMutation.isPending}
                onClick={() => adjustMutation.mutate()}
              >
                Confirm adjustment
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmAdjust(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-[140px_1fr_auto]">
            <Input
              className="h-10"
              inputMode="decimal"
              placeholder="₦ amount (+/−)"
              aria-label="Adjustment amount in naira"
              value={adjustNaira}
              onChange={(e) => setAdjustNaira(e.target.value)}
            />
            <Input
              className="h-10"
              placeholder="Reason (required, kept in audit log)"
              aria-label="Adjustment reason"
              value={adjustReason}
              onChange={(e) => setAdjustReason(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-10"
              disabled={!adjustNaira.trim() || !adjustReason.trim() || adjustMutation.isPending}
              onClick={() => setConfirmAdjust(true)}
            >
              Adjust
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
