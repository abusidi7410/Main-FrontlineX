import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/students/$studentId")({
  component: StudentProfileLayout,
});

function StudentProfileLayout() {
  return <Outlet />;
}
