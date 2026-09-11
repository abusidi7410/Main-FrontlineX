import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  GraduationCap,
  Mail,
  Pencil,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserMinus,
} from "lucide-react";
import { StatusBadge } from "@/components/common/status-badge";
import { IfAllowed } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { titleCase } from "@/lib/format";
import { ROLE_LABELS } from "@/permissions";
import {
  deleteStaff,
  getStaffMember,
  inviteStaff,
  reinstateStaff,
  suspendStaff,
} from "@/services/staff.service";
import type { StaffMember } from "@/types";

export const Route = createFileRoute("/_app/staff/$staffId")({
  head: () => ({
    meta: [
      { title: "Staff profile — Frontline Nexus" },
      {
        name: "description",
        content: "Full staff profile with role, contact details, subjects and classes.",
      },
      { property: "og:title", content: "Staff profile — Frontline Nexus" },
      {
        property: "og:description",
        content: "Full staff profile with role, contact details, subjects and classes.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StaffProfilePage,
});

function initialsOf(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

function statusTone(member: StaffMember): "success" | "warning" | "danger" {
  if (member.status === "active") return "success";
  if (member.status === "invited") return "warning";
  return "danger";
}

function StaffProfilePage() {
  const { staffId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["staff", staffId],
    queryFn: () => getStaffMember(staffId),
  });

  const invalidateStaff = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["staff", staffId] }),
      queryClient.invalidateQueries({ queryKey: ["staff"] }),
    ]);

  const suspend = useMutation({
    mutationFn: () => suspendStaff(staffId),
    onSuccess: async (member) => {
      toast.success(`${member.fullName} has been suspended.`);
      await invalidateStaff();
    },
    onError: () => toast.error("We couldn't suspend this staff member. Please try again."),
  });

  const reinstate = useMutation({
    mutationFn: () => reinstateStaff(staffId),
    onSuccess: async (member) => {
      toast.success(`${member.fullName} is active again.`);
      await invalidateStaff();
    },
    onError: () => toast.error("We couldn't reinstate this staff member. Please try again."),
  });

  const invite = useMutation({
    mutationFn: () => inviteStaff(staffId),
    onSuccess: async (member) => {
      toast.success(`Invitation sent to ${member.email}.`);
      await invalidateStaff();
    },
    onError: () =>
      toast.error("We couldn't send the invitation. Please check their email and try again."),
  });

  const remove = useMutation({
    mutationFn: () => deleteStaff(staffId),
    onSuccess: async () => {
      toast.success("The staff member has been removed.");
      await queryClient.invalidateQueries({ queryKey: ["staff"] });
      void navigate({ to: "/staff" });
    },
    onError: () => toast.error("We couldn't remove this staff member. Please try again."),
  });

  if (query.isError) {
    return (
      <ErrorState
        message="We couldn't find that staff record."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <CardsSkeleton count={2} />;

  const member = query.data;

  return (
    <div className="space-y-6">
      <Link
        to="/staff"
        className="inline-flex items-center gap-2 font-medium text-primary hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to staff
      </Link>

      <section
        className="fn-panel flex flex-wrap items-center gap-4 p-5"
        aria-label="Staff profile summary"
      >
        <Avatar className="size-16">
          <AvatarFallback className="bg-primary/10 text-lg font-semibold text-primary">
            {initialsOf(member.fullName)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[1.625rem] font-semibold leading-tight tracking-[-0.02em] sm:text-[2rem]">
            {member.fullName}
          </h1>
          <p className="mt-1 text-[15px] text-muted-foreground">
            {ROLE_LABELS[member.role]} · {member.email} · {member.phone}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={member.status} />
          <IfAllowed permission="staff.write">
            <Button asChild variant="outline">
              <Link to="/staff/$staffId/edit" params={{ staffId }}>
                <Pencil className="size-4" aria-hidden="true" /> Edit
              </Link>
            </Button>
            {member.status === "invited" ? (
              <Button variant="outline" disabled={invite.isPending} onClick={() => invite.mutate()}>
                <Mail className="size-4" aria-hidden="true" />{" "}
                {invite.isPending ? "Sending…" : "Resend invite"}
              </Button>
            ) : null}
            {member.status === "suspended" ? (
              <ConfirmDialog
                trigger={
                  <Button variant="outline">
                    <UserCheck className="size-4" aria-hidden="true" /> Reinstate
                  </Button>
                }
                title="Reinstate this staff member?"
                description={`${member.fullName} will become active again and regain access to the platform.`}
                confirmLabel="Reinstate"
                onConfirm={() => reinstate.mutate()}
              />
            ) : (
              <ConfirmDialog
                trigger={
                  <Button variant="outline">
                    <UserMinus className="size-4" aria-hidden="true" /> Suspend
                  </Button>
                }
                title="Suspend this staff member?"
                description="A suspended staff member keeps their record but loses access to the platform until reinstated."
                confirmLabel="Suspend staff member"
                destructive
                onConfirm={() => suspend.mutate()}
              />
            )}
            <ConfirmDialog
              trigger={
                <Button variant="outline" className="text-destructive hover:text-destructive">
                  <Trash2 className="size-4" aria-hidden="true" /> Delete
                </Button>
              }
              title="Remove this staff member?"
              description={`${member.fullName} will be permanently removed from your staff list. This can't be undone.`}
              confirmLabel="Delete staff member"
              destructive
              onConfirm={() => remove.mutate()}
            />
          </IfAllowed>
        </div>
      </section>

      {member.status === "suspended" ? (
        <Alert variant="destructive">
          <AlertCircle className="size-4" aria-hidden="true" />
          <AlertTitle>This staff member is suspended</AlertTitle>
          <AlertDescription>
            They currently can't sign in to the platform. Reinstate them to restore access.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Classes handled"
          value={member.classes.length}
          hint={member.classes.length > 0 ? member.classes.join(", ") : "No classes assigned yet"}
          icon={<GraduationCap className="size-4" aria-hidden="true" />}
        />
        <StatCard
          label="Subjects taught"
          value={member.subjects.length}
          hint={
            member.subjects.length > 0 ? member.subjects.join(", ") : "No subjects assigned yet"
          }
          icon={<BookOpen className="size-4" aria-hidden="true" />}
        />
        <StatCard
          label="Platform access"
          value={titleCase(member.status)}
          hint={
            member.status === "active"
              ? "Can sign in and work normally"
              : member.status === "invited"
                ? "Invited but hasn't signed in yet"
                : "Suspended — no access until reinstated"
          }
          tone={statusTone(member)}
          icon={<ShieldCheck className="size-4" aria-hidden="true" />}
        />
      </div>

      <section className="fn-panel p-5" aria-labelledby="staff-details-heading">
        <h2 id="staff-details-heading" className="font-semibold">
          Work details
        </h2>
        <dl className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">Role</dt>
            <dd className="font-medium">{ROLE_LABELS[member.role]}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Email</dt>
            <dd className="font-medium break-all">{member.email}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Phone</dt>
            <dd className="font-medium">{member.phone}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Subjects</dt>
            <dd className="font-medium">
              {member.subjects.length > 0 ? member.subjects.join(", ") : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Classes</dt>
            <dd className="font-medium">
              {member.classes.length > 0 ? member.classes.join(", ") : "—"}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
