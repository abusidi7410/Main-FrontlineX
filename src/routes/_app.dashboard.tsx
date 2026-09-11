import { createFileRoute } from "@tanstack/react-router";
import { useAuthenticatedSession } from "@/auth/session";
import { AdminDashboard } from "@/features/dashboard/admin-dashboard";
import { TeacherDashboard } from "@/features/dashboard/teacher-dashboard";
import { AccountantDashboard } from "@/features/dashboard/accountant-dashboard";
import { ParentDashboard } from "@/features/dashboard/parent-dashboard";
import { StudentDashboard } from "@/features/dashboard/student-dashboard";

export const Route = createFileRoute("/_app/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — Frontline Nexus" },
      { name: "description", content: "Your daily school overview in Frontline Nexus." },
      { property: "og:title", content: "Dashboard — Frontline Nexus" },
      { property: "og:description", content: "Your daily school overview in Frontline Nexus." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: DashboardPage,
});

function DashboardPage() {
  const { user } = useAuthenticatedSession();

  switch (user.role) {
    case "teacher":
      return <TeacherDashboard />;
    case "accountant":
      return <AccountantDashboard />;
    case "parent":
      return <ParentDashboard />;
    case "student":
      return <StudentDashboard />;
    case "principal":
      return <AdminDashboard readOnly />;
    case "secretary":
      return <AdminDashboard readOnly />;
    default:
      return <AdminDashboard />;
  }
}
