import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { setAccessToken, setUnauthorizedHandler } from "@/api/client";
import { HOME_BY_ROLE } from "@/permissions/navigation";
import { can, canAny } from "@/permissions";
import * as authService from "@/services/auth.service";
import type { AuthUser, Permission, Role } from "@/types";

interface SessionContextValue {
  session: authService.Session | null;
  status: "loading" | "authenticated" | "unauthenticated";
  signIn: (identifier: string, password: string) => Promise<authService.Session>;
  signOut: () => Promise<void>;
  updateUser: (patch: Partial<Pick<AuthUser, "fullName" | "phone">>) => void;
  can: (permission: Permission) => boolean;
  canAny: (permissions: Permission[]) => boolean;
  role: Role | null;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<authService.Session | null>(null);
  const [status, setStatus] = useState<SessionContextValue["status"]>("loading");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    const stored = authService.readStoredSession();
    setAccessToken(stored?.token ?? null);
    setSession(stored);
    setStatus(stored ? "authenticated" : "unauthenticated");
  }, []);

  useEffect(() => {
    const handleUnauthorized = async () => {
      authService.persistSession(null);
      setAccessToken(null);
      setSession(null);
      setStatus("unauthenticated");
      const redirectPath = window.location.pathname;
      await navigate({ to: "/login", replace: true, search: { redirect: redirectPath } });
    };
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  const signIn = useCallback(async (identifier: string, password: string) => {
    const next = await authService.login(identifier, password);
    authService.persistSession(next);
    setAccessToken(next.token);
    setSession(next);
    setStatus("authenticated");
    return next;
  }, []);

  const signOut = useCallback(async () => {
    await queryClient.cancelQueries();
    queryClient.clear();
    await authService.logout();
    setAccessToken(null);
    setSession(null);
    setStatus("unauthenticated");
    await navigate({ to: "/login", search: {}, replace: true });
  }, [navigate, queryClient]);

  const updateUser = useCallback((patch: Partial<Pick<AuthUser, "fullName" | "phone">>) => {
    setSession((prev) => {
      if (!prev) return prev;
      const next: authService.Session = {
        ...prev,
        user: {
          ...prev.user,
          fullName: patch.fullName ?? prev.user.fullName,
          phone: patch.phone ?? prev.user.phone,
        },
      };
      authService.persistSession(next);
      return next;
    });
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      status,
      signIn,
      signOut,
      updateUser,
      role: session?.user.role ?? null,
      can: (permission) => can(session?.user.permissions, permission),
      canAny: (permissions) => canAny(session?.user.permissions, permissions),
    }),
    [session, status, signIn, signOut, updateUser],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

/** Throws if used outside an authenticated layout. */
export function useAuthenticatedSession() {
  const ctx = useSession();
  if (!ctx.session) throw new Error("This page requires an authenticated session.");
  return { ...ctx, session: ctx.session, user: ctx.session.user, school: ctx.session.school };
}

export function homeForRole(role: Role) {
  return HOME_BY_ROLE[role];
}
