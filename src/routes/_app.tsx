import {
  createFileRoute,
  Outlet,
  redirect,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { useSession } from "@/auth/session";
import { readStoredSession } from "@/services/auth.service";

export const Route = createFileRoute("/_app")({
  ssr: false,
  beforeLoad: ({ location }) => {
    if (typeof window === "undefined") return;
    const stored = readStoredSession();
    if (!stored?.token) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
  },
  component: AppLayout,
});

function AppLayout() {
  const { status } = useSession();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    if (status === "unauthenticated") {
      void navigate({ to: "/login", replace: true, search: { redirect: pathname } });
    }
  }, [status, navigate, pathname]);

  if (status !== "authenticated") {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="size-8 animate-spin text-primary" aria-hidden="true" />
        <span className="sr-only">Checking your session…</span>
      </div>
    );
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
