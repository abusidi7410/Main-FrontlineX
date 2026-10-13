import { createFileRoute } from "@tanstack/react-router";
import { AuthScreens } from "@/features/auth/auth-screens";

export const Route = createFileRoute("/get-started")({
  head: () => ({
    meta: [
      { title: "Create your school — Frontline Nexus" },
      {
        name: "description",
        content:
          "Register your school on Frontline Nexus in a few minutes: school details, administrator account, then fund your wallet.",
      },
      { property: "og:title", content: "Create your school — Frontline Nexus" },
      {
        property: "og:description",
        content:
          "Register your school on Frontline Nexus: school details, administrator account, wallet funding.",
      },
    ],
  }),
  component: GetStartedPage,
});

function GetStartedPage() {
  return <AuthScreens initialMode="register" />;
}
