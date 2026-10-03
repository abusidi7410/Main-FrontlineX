import { Link, useRouterState } from "@tanstack/react-router";
import { ChevronsLeft, ChevronsRight, LogOut, Menu, WifiOff } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { NavIcon } from "@/components/common/icon";
import { BrandLockup, BrandMark } from "@/components/layout/brand";
import { GlobalSearch } from "@/components/layout/global-search";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { NotificationBell } from "@/components/layout/notification-bell";
import { useAuthenticatedSession } from "@/auth/session";
import { ROLE_LABELS } from "@/permissions";
import { NAV_BY_ROLE, type NavItem } from "@/permissions/navigation";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { useAppUiStore } from "@/stores/ui-store";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

function groupNav(items: NavItem[]) {
  const groups = new Map<string, NavItem[]>();
  items.forEach((item) => {
    const key = item.group ?? "Menu";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  });
  return [...groups.entries()];
}

function isActive(pathname: string, to: string) {
  if (to === "/dashboard" || to === "/platform") return pathname === to;
  return pathname === to || pathname.startsWith(`${to}/`);
}

function NavLinks({
  items,
  pathname,
  onNavigate,
  collapsed = false,
}: {
  items: NavItem[];
  pathname: string;
  onNavigate?: () => void;
  collapsed?: boolean;
}) {
  const navGroups: [string, NavItem[]][] = collapsed ? [["Menu", items]] : groupNav(items);
  return (
    <nav aria-label="Main navigation" className="space-y-5">
      {navGroups.map(([group, groupItems]) => (
        <div key={group}>
          {!collapsed ? (
            <p className="fn-eyebrow px-3 pb-2 text-sidebar-foreground/45">{group}</p>
          ) : null}
          <ul className="space-y-1">
            {groupItems.map((item) => {
              const active = isActive(pathname, item.to);
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "group relative flex min-h-[2.5rem] items-center rounded-lg text-[13px] font-medium transition-colors duration-150",
                      collapsed ? "justify-center px-0" : "gap-2.5 px-3",
                      active
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                    )}
                  >
                    {active ? (
                      <span
                        aria-hidden="true"
                        className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-sidebar-primary"
                      />
                    ) : null}
                    <NavIcon
                      name={item.icon}
                      className={cn(
                        "size-4 shrink-0",
                        active
                          ? "text-sidebar-primary"
                          : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground/90",
                      )}
                    />
                    {!collapsed ? <span className="truncate">{item.label}</span> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, school, signOut } = useAuthenticatedSession();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const online = useOnlineStatus();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { sidebarCollapsed, toggleSidebar } = useAppUiStore();
  const items = NAV_BY_ROLE[user.role];
  const bottomItems = items.filter((i) => i.mobile).slice(0, 5);
  const sidebarW = sidebarCollapsed ? "w-[5rem]" : "w-[17rem]";
  const contentPl = sidebarCollapsed ? "lg:pl-[6.75rem]" : "lg:pl-[18.5rem]";

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-xl focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <aside
        className={cn(
          "fixed inset-y-3 left-3 z-30 hidden flex-col overflow-hidden rounded-xl border border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[var(--shadow-overlay)] lg:flex",
          sidebarW,
        )}
      >
        <span
          aria-hidden="true"
          className="h-0.5 w-full shrink-0 bg-gradient-to-r from-sidebar-primary via-sidebar-primary/55 to-transparent"
        />
        <div className="flex h-16 shrink-0 items-center px-4">
          <Link
            to={user.role === "platform_manager" ? "/platform" : "/dashboard"}
            className="rounded-lg"
          >
            {sidebarCollapsed ? (
              <BrandMark />
            ) : (
              <BrandLockup tone="inverse" subtitle={school ? school.name : "Platform operations"} />
            )}
          </Link>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <NavLinks items={items} pathname={pathname} collapsed={sidebarCollapsed} />
        </div>
        {school && !sidebarCollapsed ? (
          <div className="mx-3 mb-3 rounded-lg border border-sidebar-border bg-sidebar-accent/40 px-3.5 py-3">
            <span className="inline-flex rounded-full bg-brass px-2 py-0.5 text-[11px] font-semibold text-brass-foreground">
              {school.currentSession}
            </span>
            <p className="mt-1.5 text-xs font-medium text-sidebar-foreground/70">
              {school.currentTerm}
            </p>
          </div>
        ) : null}
      </aside>

      <div className={contentPl}>
        <header className="sticky top-3 z-20 mx-0 flex h-16 items-center gap-2 rounded-xl border border-border bg-card px-3 shadow-[var(--shadow-card)] sm:px-4">
          <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
            <SheetTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                className="size-10 shrink-0 rounded-full lg:hidden"
                aria-label="Open navigation menu"
              >
                <Menu className="size-5" aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent
              side="left"
              className="w-[17rem] rounded-r-[24px] border-sidebar-border bg-sidebar p-0 text-sidebar-foreground"
            >
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <span
                aria-hidden="true"
                className="h-0.5 w-full shrink-0 bg-gradient-to-r from-sidebar-primary via-sidebar-primary/55 to-transparent"
              />
              <div className="flex h-16 items-center gap-2.5 px-4">
                <BrandMark />
                <span className="font-display text-sm font-semibold tracking-[-0.012em] text-sidebar-foreground">
                  {school?.name ?? "Frontline Nexus"}
                </span>
              </div>
              <div className="h-[calc(100vh-4rem)] overflow-y-auto px-3 py-3">
                <NavLinks
                  items={items}
                  pathname={pathname}
                  onNavigate={() => setMobileNavOpen(false)}
                />
              </div>
            </SheetContent>
          </Sheet>

          <div className="hidden min-w-0 items-center gap-2 lg:flex">
            {school ? (
              <p className="truncate text-xs text-muted-foreground">
                {school.name} · {school.currentSession} · {school.currentTerm}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Frontline Nexus platform</p>
            )}
          </div>

          {/* `min-w-0` + `shrink-0` on the pill: this row measures ~342px
              against ~336px of space at 360px, so without the constraint the
              word "Offline" wrapped onto two lines inside the pill and pushed
              the whole header into a page-level horizontal scroll. */}
          <div className="ml-auto flex min-w-0 items-center gap-2">
            {!online ? (
              <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-warning/30 bg-warning-soft px-2.5 py-1 text-xs font-medium text-warning">
                <WifiOff className="size-3.5" aria-hidden="true" /> Offline
              </span>
            ) : null}
            <GlobalSearch />
            <ThemeToggle />
            <Button
              variant="ghost"
              size="icon"
              className="hidden size-10 rounded-full lg:flex"
              onClick={toggleSidebar}
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? (
                <ChevronsRight className="size-5" aria-hidden="true" />
              ) : (
                <ChevronsLeft className="size-5" aria-hidden="true" />
              )}
            </Button>
            <NotificationBell />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  className="h-10 gap-2 rounded-full pr-2 pl-1"
                  aria-label="Account menu"
                >
                  <Avatar className="size-8">
                    <AvatarImage src={user.avatarUrl ?? undefined} alt="" />
                    <AvatarFallback className="bg-primary-soft text-sm text-primary">
                      {initials(user.fullName)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="hidden text-sm font-medium sm:inline">
                    {user.fullName.split(" ")[0]}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60 rounded-2xl p-2">
                <DropdownMenuLabel>
                  <span className="block font-semibold">{user.fullName}</span>
                  <span className="block text-xs font-normal text-muted-foreground">
                    {ROLE_LABELS[user.role]}
                  </span>
                  <span className="block text-xs font-normal text-muted-foreground">
                    {user.email}
                  </span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link to="/profile">My profile</Link>
                </DropdownMenuItem>
                {user.role !== "platform_manager" ? (
                  <DropdownMenuItem asChild>
                    <Link to="/settings">Settings</Link>
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => void signOut()}>
                  <LogOut className="mr-2 size-4" aria-hidden="true" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main
          id="main-content"
          className="mx-auto w-full max-w-[80rem] space-y-5 px-4 pb-32 pt-5 sm:px-6 lg:px-5 lg:pb-12"
        >
          <div key={pathname} className="fn-enter">
            {children}
          </div>
        </main>
      </div>

      <nav
        aria-label="Primary"
        className="fixed inset-x-3 bottom-3 z-30 grid grid-flow-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-raised)] pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {bottomItems.map((item) => {
          const active = isActive(pathname, item.to);
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex min-h-[3.5rem] flex-col items-center justify-center gap-0.5 rounded-lg px-1 text-[10px] font-medium transition-colors duration-150",
                active
                  ? "bg-brass-soft/70 text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {active ? (
                <span
                  aria-hidden="true"
                  className="absolute top-0 h-0.5 w-8 rounded-full bg-brass"
                />
              ) : null}
              <NavIcon name={item.icon} className="size-[1.125rem]" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
