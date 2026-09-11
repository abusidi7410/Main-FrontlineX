import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  GraduationCap,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserCheck,
  UserMinus,
  Users,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed, PermissionGate } from "@/components/common/permission-gate";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { numberFmt } from "@/lib/format";
import { ROLE_LABELS } from "@/permissions";
import { AssignClassesDialog } from "@/features/staff/assign-classes-dialog";
import {
  deleteStaff,
  listStaff,
  reinstateStaff,
  setStaffClasses,
  suspendStaff,
} from "@/services/staff.service";
import type { StaffMember } from "@/types";

export const Route = createFileRoute("/_app/staff")({
  head: () => ({
    meta: [
      { title: "Staff — Frontline Nexus" },
      {
        name: "description",
        content: "Teachers and administrative staff with their roles, subjects and classes.",
      },
      { property: "og:title", content: "Staff — Frontline Nexus" },
      {
        property: "og:description",
        content: "Teachers and administrative staff with roles, subjects and classes.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StaffPage,
});

function StaffPage() {
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<StaffMember | null>(null);
  const [assignTarget, setAssignTarget] = useState<StaffMember | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["staff"], queryFn: listStaff });
  const members = query.data ?? [];

  const invalidateStaff = () => queryClient.invalidateQueries({ queryKey: ["staff"] });

  const suspend = useMutation({
    mutationFn: suspendStaff,
    onSuccess: (member) => {
      toast.success(`${member.fullName} has been suspended.`);
      void invalidateStaff();
    },
    onError: () => toast.error("We couldn't suspend this staff member. Please try again."),
  });

  const reinstate = useMutation({
    mutationFn: reinstateStaff,
    onSuccess: (member) => {
      toast.success(`${member.fullName} is active again.`);
      void invalidateStaff();
    },
    onError: () => toast.error("We couldn't reinstate this staff member. Please try again."),
  });

  const remove = useMutation({
    mutationFn: deleteStaff,
    onSuccess: () => {
      toast.success("The staff member has been removed.");
      void invalidateStaff();
    },
    onError: () => toast.error("We couldn't remove this staff member. Please try again."),
  });

  const assignClasses = useMutation({
    mutationFn: ({ id, classes }: { id: string; classes: string[] }) =>
      setStaffClasses(id, classes),
    onSuccess: (member) => {
      toast.success(`${member.fullName}'s classes have been updated.`);
      setAssignTarget(null);
      void invalidateStaff();
    },
    onError: () => toast.error("We couldn't save the class assignments. Please try again."),
  });

  const term = search.trim().toLowerCase();
  const filtered = members.filter(
    (member) =>
      !term ||
      member.fullName.toLowerCase().includes(term) ||
      member.email.toLowerCase().includes(term) ||
      ROLE_LABELS[member.role].toLowerCase().includes(term),
  );

  const teachers = members.filter((m) => m.role === "teacher").length;
  const adminStaff = members.length - teachers;
  const suspendedCount = members.filter((m) => m.status === "suspended").length;

  return (
    <PermissionGate permission="staff.read">
      <div className="space-y-6">
        <PageHeader
          title="Staff"
          description="Who works at your school, what they teach and which classes they handle."
          actions={
            <IfAllowed permission="staff.write">
              <Button asChild className="h-11">
                <Link to="/staff/new">
                  <Plus className="size-4" aria-hidden="true" /> Add staff
                </Link>
              </Button>
            </IfAllowed>
          }
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Teachers"
            value={numberFmt(teachers)}
            hint="Teaching staff on the roster"
            icon={<GraduationCap className="size-4" aria-hidden="true" />}
          />
          <StatCard
            label="Admin staff"
            value={numberFmt(adminStaff)}
            hint="Bursary, secretarial and leadership roles"
            icon={<Users className="size-4" aria-hidden="true" />}
          />
          <StatCard
            label="Suspended"
            value={numberFmt(suspendedCount)}
            hint="Staff without platform access"
            tone={suspendedCount > 0 ? "warning" : "success"}
            icon={<UserMinus className="size-4" aria-hidden="true" />}
          />
        </div>

        <div className="fn-panel flex flex-col gap-3 p-4 sm:flex-row">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              className="h-11 pl-9"
              placeholder="Search staff by name, email or role"
              aria-label="Search staff"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No staff match your search"
            description="Try a different name, email or role, or clear the search box."
          />
        ) : (
          <>
            <div className="fn-panel overflow-x-auto">
              <table className="w-full min-w-[46rem] text-left">
                <caption className="sr-only">Staff roster</caption>
                <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Staff member
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Role
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Subjects
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Classes
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Phone
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
                  {filtered.map((member) => (
                    <tr key={member.id} className="hover:bg-muted/40">
                      <td className="px-4 py-3">
                        <Link
                          to="/staff/$staffId"
                          params={{ staffId: member.id }}
                          className="font-medium text-primary hover:underline"
                        >
                          {member.fullName}
                        </Link>
                        <span className="block text-sm text-muted-foreground">{member.email}</span>
                      </td>
                      <td className="px-4 py-3">{ROLE_LABELS[member.role]}</td>
                      <td className="max-w-56 px-4 py-3 text-sm text-muted-foreground">
                        {member.subjects.length > 0 ? member.subjects.join(", ") : "—"}
                      </td>
                      <td className="max-w-48 px-4 py-3 text-sm text-muted-foreground">
                        {member.classes.length > 0 ? member.classes.join(", ") : "—"}
                      </td>
                      <td className="px-4 py-3 text-sm whitespace-nowrap text-muted-foreground">
                        {member.phone}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={member.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <IfAllowed permission="staff.write">
                          <StaffRowActions
                            member={member}
                            suspendPending={suspend.isPending && suspend.variables === member.id}
                            reinstatePending={
                              reinstate.isPending && reinstate.variables === member.id
                            }
                            onSuspend={() => suspend.mutate(member.id)}
                            onReinstate={() => reinstate.mutate(member.id)}
                            onDelete={() => setDeleteTarget(member)}
                            onAssignClass={() => setAssignTarget(member)}
                          />
                        </IfAllowed>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                Showing {filtered.length} of {numberFmt(members.length)} staff members
              </p>
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Remove this staff member?"
        description={
          deleteTarget
            ? `${deleteTarget.fullName} will be permanently removed from your staff list. This can't be undone.`
            : ""
        }
        confirmLabel="Delete staff member"
        destructive
        onConfirm={() => {
          if (deleteTarget) remove.mutate(deleteTarget.id);
          setDeleteTarget(null);
        }}
      />

      <AssignClassesDialog
        member={assignTarget}
        open={assignTarget !== null}
        onOpenChange={(open) => {
          if (!open) setAssignTarget(null);
        }}
        isPending={assignClasses.isPending}
        onAssign={(classes) => {
          if (assignTarget) assignClasses.mutate({ id: assignTarget.id, classes });
        }}
      />
    </PermissionGate>
  );
}

function StaffRowActions({
  member,
  suspendPending,
  reinstatePending,
  onSuspend,
  onReinstate,
  onDelete,
  onAssignClass,
}: {
  member: StaffMember;
  suspendPending: boolean;
  reinstatePending: boolean;
  onSuspend: () => void;
  onReinstate: () => void;
  onDelete: () => void;
  onAssignClass: () => void;
}) {
  const busy = suspendPending || reinstatePending;

  return (
    <div className="flex items-center justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={suspendPending || reinstatePending}>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`More actions for ${member.fullName}`}
            disabled={suspendPending || reinstatePending}
          >
            <MoreHorizontal aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuLabel>{member.fullName}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={busy}
            onClick={() => {
              if (member.status === "suspended") onReinstate();
              else onSuspend();
            }}
          >
            {member.status === "suspended" ? (
              <UserCheck aria-hidden="true" />
            ) : (
              <UserMinus aria-hidden="true" />
            )}
            {member.status === "suspended" ? "Reinstate" : "Suspend"}
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link to="/staff/$staffId/edit" params={{ staffId: member.id }}>
              <Pencil aria-hidden="true" /> Edit details
            </Link>
          </DropdownMenuItem>
          {member.role === "teacher" ? (
            <DropdownMenuItem onClick={onAssignClass}>
              <GraduationCap aria-hidden="true" /> Assign classes
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={onDelete}>
            <Trash2 aria-hidden="true" /> Delete staff member
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
