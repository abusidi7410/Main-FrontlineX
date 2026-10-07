import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Copy,
  GraduationCap,
  KeyRound,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserMinus,
  Users,
  Wallet,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { StatCard } from "@/components/common/stat-card";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiRequestError } from "@/api/client";
import { useAuthenticatedSession } from "@/auth/session";
import { useDebounced } from "@/hooks/use-debounced";
import { dateFmt, numberFmt } from "@/lib/format";
import { provisionableRoles, ROLE_LABELS } from "@/permissions";
import { getAcademicStructure } from "@/services/academics.service";
import {
  assignClassTeacher,
  getClassTeachers,
  type ClassTeacherAssignment,
} from "@/services/attendance.service";
import {
  createAccount,
  deleteAccount,
  getAccountStats,
  listAccounts,
  resetAccountPassword,
  setAccountStatus,
  type CreatedAccount,
} from "@/services/accounts.service";
import type { DefaultCredentials, Role, SchoolAccount } from "@/types";

export const Route = createFileRoute("/_app/accounts")({
  head: () => ({
    meta: [
      { title: "Accounts — Frontline Nexus" },
      {
        name: "description",
        content: "Login accounts for students, teachers, admins and finance staff at your school.",
      },
      { property: "og:title", content: "Accounts — Frontline Nexus" },
      {
        property: "og:description",
        content: "Manage login accounts for everyone at your school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AccountsPage,
});

const PROVISIONABLE_ROLES: Role[] = [
  "school_admin",
  "principal",
  "teacher",
  "accountant",
  "secretary",
  "student",
  "parent",
];

const ROLE_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All roles" },
  ...PROVISIONABLE_ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] })),
];

const EMPTY_FORM = {
  fullName: "",
  email: "",
  phone: "",
  role: "teacher" as Role,
  password: "",
  admissionNumber: "",
};

function AccountsPage() {
  const { user, can } = useAuthenticatedSession();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebounced(search, 300);

  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [resetTarget, setResetTarget] = useState<SchoolAccount | null>(null);
  const [resetCreds, setResetCreds] = useState<DefaultCredentials | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SchoolAccount | null>(null);
  const [assignTarget, setAssignTarget] = useState<SchoolAccount | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["account-stats"] });
  };

  const accounts = useQuery({
    queryKey: ["accounts", { search: debouncedSearch, role, status, page }],
    queryFn: () => listAccounts({ search: debouncedSearch, role, status, page }),
  });
  const stats = useQuery({ queryKey: ["account-stats"], queryFn: getAccountStats });

  // Class-teacher designations, shown in the linked-record cell and used
  // by the assign-class dialog. Reads are open to every school member;
  // writes need `staff.write`, which the API enforces regardless of what
  // this renders.
  const classTeachers = useQuery({
    queryKey: ["class-teachers"],
    queryFn: getClassTeachers,
  });
  // The class list lives in the academic structure, which requires
  // `academics.read` — only fetched for roles that can assign at all.
  const academics = useQuery({
    queryKey: ["academics"],
    queryFn: getAcademicStructure,
    enabled: can("staff.write"),
  });

  // The API only lets a manager provision roles inside their own matrix, so
  // the dialog must offer exactly this set — `teacher` (the old default) is
  // not creatable by a secretary, for instance.
  const allowedRoles = provisionableRoles(user.role);

  const createMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: (data) => {
      invalidate();
      if (data.defaultCredentials) {
        setCreated(data);
      } else {
        toast.success(`${data.fullName} now has a login account.`);
        setCreateOpen(false);
      }
    },
    onError: (error) => {
      // Field-level failures are rendered inside the dialog, next to the input
      // that caused them. Toasting the generic DRF sentence turned a plain
      // validation error ("email already taken", "role not allowed") into an
      // unexplained failure that made the whole module look broken.
      const fieldErrors = error instanceof ApiRequestError ? error.fieldErrors : undefined;
      if (fieldErrors && Object.keys(fieldErrors).length > 0) return;
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "We couldn't create that account. Please try again.",
        { duration: 6000 },
      );
    },
  });

  const resetMutation = useMutation({
    mutationFn: (id: string) => resetAccountPassword(id),
    onSuccess: (data) => {
      setResetCreds(data.defaultCredentials);
      invalidate();
    },
    onError: () => toast.error("We couldn't reset that password. Please try again."),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status: s }: { id: string; status: "active" | "inactive" }) =>
      setAccountStatus(id, s),
    onSuccess: (account) => {
      toast.success(
        account.status === "active"
          ? `${account.fullName} can sign in again.`
          : `${account.fullName} has been deactivated.`,
      );
      invalidate();
    },
    onError: (error) => toast.error(`${error.message} Please try again.`, { duration: 6000 }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      toast.success("The account has been deleted.");
      setDeleteTarget(null);
      invalidate();
    },
    onError: (error) => toast.error(`${error.message} Please try again.`, { duration: 6000 }),
  });

  const assignClassMutation = useMutation({
    mutationFn: (input: { className: string; staffId: string }) => assignClassTeacher(input),
    onSuccess: (data) => {
      toast.success(`${data.classTeacher} is now the class teacher for ${data.className}.`);
      setAssignTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["class-teachers"] });
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (error) => toast.error(`${error.message} Please try again.`, { duration: 6000 }),
  });

  const classesForTeacher = (staffId: string) =>
    (classTeachers.data?.assignments ?? []).filter((row) => row.staffId === staffId);

  const data = accounts.data;
  const byRole = stats.data?.byRole;
  const busyId =
    resetMutation.isPending && resetTarget
      ? resetTarget.id
      : statusMutation.isPending
        ? ((statusMutation.variables as { id?: string } | undefined)?.id ?? null)
        : assignClassMutation.isPending && assignTarget
          ? assignTarget.id
          : null;

  return (
    <PermissionGate permission="accounts.read">
      <div className="space-y-6">
        <PageHeader
          title="Accounts"
          description="Login accounts for students, teachers, admins and finance staff."
          actions={
            <IfAllowed permission="accounts.write">
              <Button className="h-11" onClick={() => setCreateOpen(true)}>
                <Plus className="size-4" aria-hidden="true" /> Add account
              </Button>
            </IfAllowed>
          }
        />

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Students"
            value={byRole ? `${byRole.student.active}/${byRole.student.total} active` : "—"}
            hint="Active student logins"
            icon={<Users className="size-4" aria-hidden="true" />}
          />
          <StatCard
            label="Teachers"
            value={byRole ? `${byRole.teacher.active}/${byRole.teacher.total} active` : "—"}
            hint="Active teacher logins"
            icon={<GraduationCap className="size-4" aria-hidden="true" />}
          />
          <StatCard
            label="Admins"
            value={
              byRole ? `${byRole.school_admin.active}/${byRole.school_admin.total} active` : "—"
            }
            hint="School administrator logins"
            icon={<ShieldCheck className="size-4" aria-hidden="true" />}
          />
          <StatCard
            label="Finance"
            value={byRole ? `${byRole.accountant.active}/${byRole.accountant.total} active` : "—"}
            hint="Bursar / accountant logins"
            icon={<Wallet className="size-4" aria-hidden="true" />}
          />
        </div>

        <div className="fn-panel flex flex-col gap-3 p-4 lg:flex-row">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              className="h-11 pl-9"
              placeholder="Search by name or email"
              aria-label="Search accounts"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
          <Select
            value={role}
            onValueChange={(value) => {
              setRole(value);
              setPage(1);
            }}
          >
            <SelectTrigger className="h-11 w-full sm:w-48" aria-label="Filter by role">
              <SelectValue placeholder="All roles" />
            </SelectTrigger>
            <SelectContent>
              {ROLE_FILTER_OPTIONS.map((option) => (
                <SelectItem key={option.value || "all"} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          >
            <SelectTrigger className="h-11 w-full sm:w-40" aria-label="Filter by status">
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Any status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {accounts.isError ? (
          <ErrorState onRetry={() => void accounts.refetch()} />
        ) : accounts.isPending ? (
          <ListSkeleton />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            title="No accounts found"
            description="Adjust your search or filters, or add a new account."
          />
        ) : (
          <>
            <div className="fn-panel overflow-x-auto">
              <table className="w-full min-w-[48rem] text-left">
                <caption className="sr-only">School login accounts</caption>
                <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Account
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Role
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Linked record
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Last login
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Status
                    </th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.results.map((account) => (
                    <tr key={account.id} className="hover:bg-muted/40">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 font-medium">
                          {account.fullName}
                          {account.mustChangePassword ? (
                            <span
                              className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning"
                              title="Password must be changed on next sign in"
                            >
                              New password
                            </span>
                          ) : null}
                        </div>
                        <span className="block text-sm text-muted-foreground">{account.email}</span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{ROLE_LABELS[account.role]}</td>
                      <td className="max-w-56 px-4 py-3 text-sm text-muted-foreground">
                        {account.student ? (
                          <>
                            {account.student.admissionNumber}
                            <span className="block">{account.student.className}</span>
                          </>
                        ) : account.staff ? (
                          <>
                            {account.staff.fullName}
                            {account.role === "teacher" &&
                            classesForTeacher(account.staff.id).length > 0 ? (
                              <span className="block">
                                {classesForTeacher(account.staff.id)
                                  .map((row) => row.className)
                                  .join(", ")}
                              </span>
                            ) : null}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm whitespace-nowrap text-muted-foreground">
                        {account.lastLogin ? dateFmt(account.lastLogin) : "Never"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={account.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        {account.id !== user.id ? (
                          <AccountRowActions
                            account={account}
                            busy={busyId === account.id}
                            onResetPassword={() => setResetTarget(account)}
                            onToggleStatus={() =>
                              statusMutation.mutate({
                                id: account.id,
                                status: account.status === "active" ? "inactive" : "active",
                              })
                            }
                            onDelete={() => setDeleteTarget(account)}
                            onAssignClass={
                              account.role === "teacher" && account.staff
                                ? () => setAssignTarget(account)
                                : undefined
                            }
                          />
                        ) : (
                          <span className="text-sm text-muted-foreground">You</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                Showing {numberFmt((data.page - 1) * data.pageSize + (data.results.length || 0))} of{" "}
                {numberFmt(data.count)} accounts
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1 || accounts.isFetching}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">Page {data.page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page * data.pageSize >= data.count || accounts.isFetching}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      <CreateAccountDialog
        open={createOpen}
        onOpenChange={(open) => {
          if (!open && !createMutation.isPending) {
            setCreateOpen(false);
            setCreated(null);
            createMutation.reset();
          }
        }}
        isPending={createMutation.isPending}
        created={created}
        allowedRoles={allowedRoles}
        error={createMutation.error instanceof ApiRequestError ? createMutation.error : null}
        clearError={createMutation.reset}
        onClose={() => {
          setCreateOpen(false);
          setCreated(null);
          createMutation.reset();
        }}
        onSubmit={(input) => createMutation.mutate(input)}
      />

      <ResetPasswordDialog
        target={resetTarget}
        isPending={resetMutation.isPending}
        credentials={resetCreds}
        onOpenChange={(open) => {
          if (!open) {
            setResetTarget(null);
            setResetCreds(null);
          }
        }}
        onConfirm={(id) => {
          setResetCreds(null);
          resetMutation.mutate(id);
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setDeleteTarget(null);
        }}
        title="Delete this account?"
        description={
          deleteTarget
            ? `${deleteTarget.fullName} (${deleteTarget.email}) will lose all access to the platform. This can't be undone.`
            : ""
        }
        confirmLabel="Delete account"
        destructive
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
      />

      <AssignClassDialog
        target={assignTarget}
        isPending={assignClassMutation.isPending}
        classes={academics.data?.classes ?? []}
        assignments={classTeachers.data?.assignments ?? []}
        onOpenChange={(open) => {
          if (!open && !assignClassMutation.isPending) setAssignTarget(null);
        }}
        onConfirm={(className) => {
          if (assignTarget?.staff) {
            assignClassMutation.mutate({ className, staffId: assignTarget.staff.id });
          }
        }}
      />
    </PermissionGate>
  );
}

function AccountRowActions({
  account,
  busy,
  onResetPassword,
  onToggleStatus,
  onDelete,
  onAssignClass,
}: {
  account: SchoolAccount;
  busy: boolean;
  onResetPassword: () => void;
  onToggleStatus: () => void;
  onDelete: () => void;
  onAssignClass?: (() => void) | undefined;
}) {
  return (
    <div className="flex items-center justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={busy}>
          <Button variant="ghost" size="icon" aria-label={`More actions for ${account.fullName}`}>
            <MoreHorizontal aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>{account.fullName}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onResetPassword}>
            <RefreshCw aria-hidden="true" /> Reset password
          </DropdownMenuItem>
          {onAssignClass ? (
            <IfAllowed permission="staff.write">
              <DropdownMenuItem onClick={onAssignClass}>
                <GraduationCap aria-hidden="true" /> Assign class…
              </DropdownMenuItem>
            </IfAllowed>
          ) : null}
          <DropdownMenuItem onClick={onToggleStatus}>
            {account.status === "active" ? (
              <UserMinus aria-hidden="true" />
            ) : (
              <UserCheck aria-hidden="true" />
            )}
            {account.status === "active" ? "Deactivate" : "Activate"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={onDelete}>
            <Trash2 aria-hidden="true" /> Delete account
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function CreateAccountDialog({
  open,
  onOpenChange,
  isPending,
  created,
  allowedRoles,
  error,
  clearError,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPending: boolean;
  created: CreatedAccount | null;
  allowedRoles: Role[];
  error: ApiRequestError | null;
  clearError: () => void;
  onClose: () => void;
  onSubmit: (input: {
    fullName: string;
    email: string;
    phone?: string;
    role: Role;
    password?: string;
    admissionNumber?: string;
  }) => void;
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [copyLabel, setCopyLabel] = useState<string | null>(null);

  // Start on a role this user is actually allowed to provision; the API
  // rejects anything outside the caller's matrix with a 400.
  const defaultRole: Role = allowedRoles.includes("teacher")
    ? "teacher"
    : (allowedRoles[0] ?? "teacher");

  useEffect(() => {
    if (open && !created) setForm({ ...EMPTY_FORM, role: defaultRole });
  }, [open, created, defaultRole]);

  const update = (patch: Partial<typeof EMPTY_FORM>) => {
    setForm((current) => ({ ...current, ...patch }));
    // Without this the previous failure stays pinned under a field the user
    // has already corrected.
    clearError();
  };

  const fieldErrors = error?.fieldErrors;
  // Errors for inputs that are on screen are shown under them; everything else
  // (a missing `studentId`, a hidden `password` field) goes to the summary box
  // so no rejection can be invisible.
  const visibleFields = new Set([
    "fullName",
    "email",
    "role",
    "phone",
    form.role === "student" ? "admissionNumber" : "password",
  ]);
  const hiddenErrors = Object.entries(fieldErrors ?? {}).filter(([key]) => !visibleFields.has(key));

  const copyText = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text).catch(() => undefined);
    setCopyLabel(label);
    setTimeout(() => setCopyLabel(null), 1600);
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const input: {
      fullName: string;
      email: string;
      role: Role;
      phone?: string;
      password?: string;
      admissionNumber?: string;
    } = {
      fullName: form.fullName,
      email: form.email,
      role: form.role,
    };
    if (form.phone) input.phone = form.phone;
    if (form.password) input.password = form.password;
    if (form.role === "student" && form.admissionNumber) {
      input.admissionNumber = form.admissionNumber;
    }
    onSubmit(input);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(openChange) => {
        if (openChange && created) return;
        onOpenChange(openChange);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-lg">
            {created ? "Account created" : "Add an account"}
          </DialogTitle>
        </DialogHeader>
        {created?.defaultCredentials ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              The account is ready. This is the only time these credentials are shown — share them
              securely and the account must change the password at first sign in.
            </p>
            <div className="space-y-3 rounded-lg border p-4">
              <FieldRow
                label="Email"
                value={created.defaultCredentials.email}
                copied={copyLabel === "email"}
                onCopy={() => void copyText(created.defaultCredentials?.email ?? "", "email")}
              />
              <FieldRow
                label="Temporary password"
                value={created.defaultCredentials.password}
                copied={copyLabel === "password"}
                onCopy={() => void copyText(created.defaultCredentials?.password ?? "", "password")}
              />
            </div>
            <DialogFooter>
              <Button className="w-full" onClick={onClose}>
                Done
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            {hiddenErrors.length > 0 ? (
              <div
                role="alert"
                className="rounded-lg border border-destructive/40 bg-destructive/10 p-3"
              >
                <p className="text-sm font-medium text-destructive">Check these details:</p>
                <ul className="mt-1 list-inside list-disc text-sm text-destructive">
                  {hiddenErrors.map(([key, message]) => (
                    <li key={key}>{message}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="acc-name">Full name</Label>
              <Input
                id="acc-name"
                className="h-11"
                required
                placeholder="e.g. Ibrahim Musa"
                value={form.fullName}
                onChange={(event) => update({ fullName: event.target.value })}
              />
              <FieldError message={fieldErrors?.["fullName"]} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="acc-email">Email</Label>
                <Input
                  id="acc-email"
                  type="email"
                  className="h-11"
                  required
                  placeholder="name@school.edu.ng"
                  value={form.email}
                  onChange={(event) => update({ email: event.target.value })}
                />
                <FieldError message={fieldErrors?.["email"]} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="acc-role">Role</Label>
                <Select value={form.role} onValueChange={(role) => update({ role: role as Role })}>
                  <SelectTrigger className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {allowedRoles.map((role) => (
                      <SelectItem key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError message={fieldErrors?.["role"]} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="acc-phone">Phone</Label>
                <Input
                  id="acc-phone"
                  className="h-11"
                  placeholder="+234..."
                  value={form.phone}
                  onChange={(event) => update({ phone: event.target.value })}
                />
                <FieldError message={fieldErrors?.["phone"]} />
              </div>
              {form.role === "student" ? (
                <div className="space-y-2">
                  <Label htmlFor="acc-admission">Admission number</Label>
                  <Input
                    id="acc-admission"
                    className="h-11"
                    required
                    placeholder="e.g. ALP-001"
                    value={form.admissionNumber}
                    onChange={(event) => update({ admissionNumber: event.target.value })}
                  />
                  <FieldError message={fieldErrors?.["admissionNumber"]} />
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="acc-password">Password (optional)</Label>
                  <Input
                    id="acc-password"
                    type="password"
                    className="h-11"
                    placeholder="Auto-generated if blank"
                    value={form.password}
                    onChange={(event) => update({ password: event.target.value })}
                  />
                  <FieldError message={fieldErrors?.["password"]} />
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Leave the password blank and a temporary one is created and shown to you only once —
              the account must change it on first sign in.
            </p>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending ? "Creating…" : "Create account"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({
  target,
  isPending,
  credentials,
  onOpenChange,
  onConfirm,
}: {
  target: SchoolAccount | null;
  isPending: boolean;
  credentials: DefaultCredentials | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: (id: string) => void;
}) {
  const [copyLabel, setCopyLabel] = useState<string | null>(null);

  const copyText = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text).catch(() => undefined);
    setCopyLabel(label);
    setTimeout(() => setCopyLabel(null), 1600);
  };

  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (open && credentials) return;
        onOpenChange(open);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg">
            {credentials ? "Password reset" : `Reset password — ${target?.fullName ?? ""}`}
          </DialogTitle>
        </DialogHeader>
        {credentials ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              A temporary password was issued. This is the only time you can see it.
            </p>
            <div className="space-y-3 rounded-lg border p-4">
              <FieldRow
                label="Email"
                value={credentials.email}
                copied={copyLabel === "email"}
                onCopy={() => void copyText(credentials.email, "email")}
              />
              <FieldRow
                label="Temporary password"
                value={credentials.password}
                copied={copyLabel === "password"}
                onCopy={() => void copyText(credentials.password, "password")}
              />
            </div>
            <DialogFooter>
              <Button className="w-full" onClick={() => onOpenChange(false)}>
                Done
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              This revokes the current password and issues a temporary one the account must change
              at the next sign in.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={isPending} onClick={() => target && onConfirm(target.id)}>
                {isPending ? "Resetting…" : "Reset password"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AssignClassDialog({
  target,
  isPending,
  classes,
  assignments,
  onOpenChange,
  onConfirm,
}: {
  target: SchoolAccount | null;
  isPending: boolean;
  classes: string[];
  assignments: ClassTeacherAssignment[];
  onOpenChange: (open: boolean) => void;
  onConfirm: (className: string) => void;
}) {
  const [className, setClassName] = useState("");

  useEffect(() => {
    if (target) setClassName("");
  }, [target]);

  const staffId = target?.staff?.id;
  const currentClasses = staffId ? assignments.filter((row) => row.staffId === staffId) : [];
  const selectedHolder = className
    ? assignments.find((row) => row.className === className)
    : undefined;
  // One class has exactly one class teacher, so picking a class that is
  // already somebody else's replaces that designation.
  const replacesOther = !!selectedHolder && !!staffId && selectedHolder.staffId !== staffId;

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg">Assign class — {target?.fullName ?? ""}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The class teacher is the only one who can take that class&apos;s daily register (a
            school admin can always submit it too).
          </p>
          <div className="space-y-1.5">
            <Label>Currently assigned</Label>
            {currentClasses.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {currentClasses.map((row) => (
                  <span
                    key={row.className}
                    className="rounded-full border bg-muted/50 px-3 py-1 text-sm"
                  >
                    {row.className}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No class yet.</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="assign-class">Class</Label>
            <Select value={className} onValueChange={setClassName}>
              <SelectTrigger className="h-11">
                <SelectValue placeholder="Choose a class" />
              </SelectTrigger>
              <SelectContent>
                {classes.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {classes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No classes yet — add them on the Academics screen first.
              </p>
            ) : replacesOther ? (
              <p className="text-sm text-warning">
                {selectedHolder?.staffName} currently holds this class and will be replaced.
              </p>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button
            disabled={!className || isPending || classes.length === 0}
            onClick={() => {
              if (className) onConfirm(className);
            }}
          >
            {isPending ? "Assigning…" : "Assign class"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FieldError({ message }: { message?: string | undefined }) {
  if (!message) return null;
  return <p className="text-sm text-destructive">{message}</p>;
}

function FieldRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label>{label}</Label>
        <Button type="button" variant="ghost" size="sm" onClick={onCopy}>
          {copied ? "Copied" : "Copy"}
          <Copy className="ml-1.5 size-3.5" aria-hidden="true" />
        </Button>
      </div>
      <div className="rounded-md border bg-muted/50 px-3 py-2 font-mono text-sm break-all">
        {value}
      </div>
    </div>
  );
}
