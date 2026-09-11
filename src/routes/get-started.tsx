import { createFileRoute } from "@tanstack/react-router";
import { AuthScreens } from "@/features/auth/auth-screens";

export const Route = createFileRoute("/get-started")({
  validateSearch: (search: Record<string, unknown>): { tier?: string } =>
    typeof search["tier"] === "string" && search["tier"] ? { tier: search["tier"] } : {},
  head: () => ({
    meta: [
      { title: "Create your school — Frontline Nexus" },
      {
        name: "description",
        content:
          "Register your school on Frontline Nexus in a few minutes: school details, administrator account, subscription and activation.",
      },
      { property: "og:title", content: "Create your school — Frontline Nexus" },
      {
        property: "og:description",
        content:
          "Register your school on Frontline Nexus: school details, administrator account, subscription, activation.",
      },
    ],
  }),
  component: GetStartedPage,
});

function GetStartedPage() {
  const { tier } = Route.useSearch();
  return <AuthScreens initialMode="register" initialTier={tier} />;
}
