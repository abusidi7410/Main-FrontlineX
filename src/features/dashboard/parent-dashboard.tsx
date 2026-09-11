import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { useAuthenticatedSession } from "@/auth/session";
import { greeting, initials, naira, percent } from "@/lib/format";
import { listStudents } from "@/services/students.service";
import { getAnnouncements } from "@/services/school.service";
import { cn } from "@/lib/utils";

/** In live mode this comes from /parents/me/children. */
function useChildren() {
  return useQuery({
    queryKey: ["children"],
    queryFn: () => listStudents({ pageSize: 3 }),
    select: (page) => page.results,
  });
}

export function ParentDashboard() {
  const { user } = useAuthenticatedSession();
  const children = useChildren();
  const announcements = useQuery({ queryKey: ["announcements"], queryFn: getAnnouncements });
  const [activeId, setActiveId] = useState<string | null>(null);

  if (children.isError) return <ErrorState onRetry={() => void children.refetch()} />;
  if (children.isPending) return <CardsSkeleton count={3} />;

  const list = children.data ?? [];
  const active = list.find((c) => c.id === activeId) ?? list[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">
          {greeting()}, {user.fullName}.
        </h1>
        <p className="mt-1 text-muted-foreground">Here's how your children are doing this term.</p>
      </div>

      {list.length > 1 ? (
        <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Select a child">
          {list.map((child) => {
            const selected = child.id === active?.id;
            return (
              <button
                key={child.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setActiveId(child.id)}
                className={cn(
                  "flex min-h-12 shrink-0 items-center gap-2 rounded-full border px-4 font-medium transition-colors",
                  selected
                    ? "border-primary bg-primary-soft text-primary"
                    : "bg-surface hover:bg-muted",
                )}
              >
                <Avatar className="size-7">
                  <AvatarFallback className="bg-muted text-xs">
                    {initials(`${child.firstName} ${child.lastName}`)}
                  </AvatarFallback>
                </Avatar>
                {child.firstName}
              </button>
            );
          })}
        </div>
      ) : null}

      {active ? (
        <>
          <div className="fn-panel p-5">
            <div className="flex items-center gap-3">
              <Avatar className="size-12">
                <AvatarFallback className="bg-primary-soft text-primary">
                  {initials(`${active.firstName} ${active.lastName}`)}
                </AvatarFallback>
              </Avatar>
              <div>
                <p className="font-display text-lg font-semibold">
                  {active.firstName} {active.lastName}
                </p>
                <p className="text-muted-foreground">
                  {active.className}
                  {active.arm} · {active.admissionNumber}
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Attendance"
              value={percent(active.attendanceRate)}
              tone={active.attendanceRate >= 75 ? "success" : "warning"}
            />
            <StatCard label="Term average" value={percent(active.average)} />
            <StatCard
              label="Outstanding fees"
              value={naira(active.outstandingFees)}
              tone={active.outstandingFees > 0 ? "warning" : "success"}
            />
          </div>
        </>
      ) : null}

      <QuickActions
        actions={[
          { label: "View results", to: "/children", icon: "award" },
          { label: "View attendance", to: "/children", icon: "clipboard" },
          { label: "Pay fees", to: "/fees", icon: "wallet" },
          { label: "Announcements", to: "/communication", icon: "megaphone" },
          { label: "Ask the AI assistant", to: "/ai", icon: "sparkles" },
        ]}
      />

      <section className="fn-panel overflow-hidden" aria-labelledby="ann-heading">
        <div className="border-b px-5 py-4">
          <h2 id="ann-heading" className="font-semibold">
            From the school
          </h2>
        </div>
        {announcements.data && announcements.data.length > 0 ? (
          <ul className="divide-y">
            {announcements.data.slice(0, 3).map((item) => (
              <li key={item.id} className="px-5 py-4">
                <p className="font-medium">{item.title}</p>
                <p className="mt-1 text-muted-foreground">{item.body}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-center text-muted-foreground">No announcements yet.</p>
        )}
        <div className="border-t px-5 py-3">
          <Link to="/communication" className="font-medium text-primary hover:underline">
            See all announcements
          </Link>
        </div>
      </section>
    </div>
  );
}
