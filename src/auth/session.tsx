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
import type { AuthUser, Permission, Role, School } from "@/types";

interface SessionContextValue {
  session: authService.Session | null;
  status: "loading" | "authenticated" | "unauthenticated";
  signIn: (identifier: string, password: string) => Promise<authService.Session>;
  signOut: () => Promise<void>;
  updateUser: (
    patch: Partial<Pick<AuthUser, "fullName" | "phone" | "avatarUrl" | "mustChangePassword">>,
  ) => void;
  updateSchool: (patch: Partial<School>) => void;
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
    const handleUnauthorized = async (reason: string | undefined) => {
      authService.persistSession(null);
      setAccessToken(null);
      setSession(null);
      setStatus("unauthenticated");
      const redirectPath = window.location.pathname;
      await navigate({
        to: "/login",
        replace: true,
        search: { redirect: redirectPath, ...(reason === undefined ? {} : { reason }) },
      });
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

  const updateUser = useCallback(
    (
      patch: Partial<Pick<AuthUser, "fullName" | "phone" | "avatarUrl" | "mustChangePassword">>,
    ) => {
      setSession((prev) => {
        if (!prev) return prev;
        const next: authService.Session = {
          ...prev,
          user: { ...prev.user, ...patch },
        };
        authService.persistSession(next);
        return next;
      });
    },
    [],
  );

  const updateSchool = useCallback(
    (patch: Partial<School>) => {
      setSession((prev) => {
        if (!prev?.school) return prev;
        const next: authService.Session = {
          ...prev,
          school: { ...prev.school, ...patch },
        };
        authService.persistSession(next);
        setSession(next);
        return next;
      });
    },
    [],
  );

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      status,
      signIn,
      signOut,
      updateUser,
      updateSchool,
      role: session?.user.role ?? null,
      can: (permission) => can(session?.user.permissions, permission),
      canAny: (permissions) => canAny(session?.user.permissions, permissions),
    }),
    [session, status, signIn, signOut, updateUser, updateSchool],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

/** Throws if used outside an authenticated layout. */
// eslint-disable-next-line react-refresh/only-export-components
export function useAuthenticatedSession() {
  const ctx = useSession();
  if (!ctx.session) throw new Error("This page requires an authenticated session.");
  return { ...ctx, session: ctx.session, user: ctx.session.user, school: ctx.session.school };
}

// eslint-disable-next-line react-refresh/only-export-components
export function homeForRole(role: Role) {
  return HOME_BY_ROLE[role];
}
