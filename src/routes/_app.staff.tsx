import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/staff")({
  // The Staff module has been folded into Accounts: staff listings and
  // provisioning now live under /accounts (staff-role accounts keep a
  // StaffMember row in sync automatically). Redirect any legacy /staff URL.
  beforeLoad: () => {
    throw redirect({ to: "/accounts" });
  },
  component: StaffLayout,
});

function StaffLayout() {
  return <Outlet />;
}
