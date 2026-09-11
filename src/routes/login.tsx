import { createFileRoute } from "@tanstack/react-router";
import { AuthScreens } from "@/features/auth/auth-screens";

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => {
    if (typeof search["redirect"] === "string") return { redirect: search["redirect"] };
    return {};
  },
  head: () => ({
    meta: [
      { title: "Sign in — Frontline Nexus" },
      { name: "description", content: "Sign in to your Frontline Nexus school account." },
      { property: "og:title", content: "Sign in — Frontline Nexus" },
      { property: "og:description", content: "Sign in to your Frontline Nexus school account." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const { redirect } = Route.useSearch();
  return <AuthScreens initialMode="login" redirectTo={redirect ?? undefined} />;
}
