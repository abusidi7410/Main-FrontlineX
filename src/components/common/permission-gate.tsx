import { Link } from "@tanstack/react-router";
import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/auth/session";
import type { Permission } from "@/types";

/**
 * UI-level gate. Authorisation is always re-checked by the API — this only
 * prevents showing controls and data the current role has no business seeing.
 */
export function PermissionGate({
  permission,
  anyOf,
  children,
}: {
  permission?: Permission;
  anyOf?: Permission[];
  children: ReactNode;
}) {
  const { can, canAny } = useSession();
  const allowed = permission ? can(permission) : anyOf ? canAny(anyOf) : true;
  if (allowed) return <>{children}</>;

  return (
    <div className="fn-panel flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <ShieldAlert className="size-6" aria-hidden="true" />
      </div>
      <h2 className="text-lg font-semibold">You don't have access to this area</h2>
      <p className="max-w-md text-muted-foreground">
        Your role doesn't include permission for this page. If you need access, ask your school
        administrator to update your permissions.
      </p>
      <Button asChild variant="outline" className="mt-2">
        <Link to="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}

export function IfAllowed({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { can } = useSession();
  return can(permission) ? <>{children}</> : null;
}
