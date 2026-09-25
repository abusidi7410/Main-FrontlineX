import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/staff/$staffId")({
  component: StaffProfileLayout,
});

function StaffProfileLayout() {
  return <Outlet />;
}
