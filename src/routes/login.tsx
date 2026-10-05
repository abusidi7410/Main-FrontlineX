import { createFileRoute } from "@tanstack/react-router";
import { AuthScreens } from "@/features/auth/auth-screens";

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string; reason?: string } => {
    const out: { redirect?: string; reason?: string } = {};
    if (typeof search["redirect"] === "string") out.redirect = search["redirect"];
    if (typeof search["reason"] === "string") out.reason = search["reason"];
    return out;
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
  const { redirect, reason } = Route.useSearch();
  return (
    <AuthScreens
      initialMode="login"
      redirectTo={redirect ?? undefined}
      initialServerError={reason ?? undefined}
    />
  );
}
