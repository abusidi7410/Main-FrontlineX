import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Activity,
  Building2,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Download,
  Phone,
  RefreshCcw,
  TrendingDown,
  TrendingUp,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SUBSCRIPTION_TIERS } from "@/constants/plans";
import { compactNaira, dateFmt, naira, numberFmt, titleCase } from "@/lib/format";
import { getPlatformOverview } from "@/services/platform.service";
import type {
  AtRiskSchool,
  PlatformOverview as PlatformOverviewData,
  PlatformOverviewRange,
  SchoolStatus,
} from "@/types";

export const Route = createFileRoute("/_app/platform/")({
  head: () => ({
    meta: [
      { title: "Platform overview — Frontline Nexus" },
      {
        name: "description",
        content: "Tenant health, revenue and adoption across every school on Frontline Nexus.",
      },
      { property: "og:title", content: "Platform overview — Frontline Nexus" },
      {
        property: "og:description",
        content: "Tenant health, revenue and adoption across every school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformOverview,
});

const RANGE_OPTIONS: { value: PlatformOverviewRange; label: string }[] = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

const STATUS_META: { status: SchoolStatus; label: string; color: string }[] = [
  { status: "active", label: "Active", color: "var(--success)" },
  { status: "trial", label: "Trial", color: "var(--info)" },
  { status: "grace", label: "Grace", color: "var(--warning)" },
  { status: "pending_payment", label: "Pending payment", color: "var(--chart-3)" },
  { status: "suspended", label: "Suspended", color: "var(--destructive)" },
];

const REVENUE_CHART_CONFIG = {
  revenue: { label: "Revenue", color: "var(--primary)" },
};

function isPlatformRange(value: string): value is PlatformOverviewRange {
  return value === "7d" || value === "30d" || value === "90d";
}

function percentageChange(values: number[]) {
  const current = values.at(-1) ?? 0;
  const previous = values.at(-2) ?? 0;
  if (previous === 0) return current === 0 ? 0 : 100;
  return ((current - previous) / Math.abs(previous)) * 100;
}

function Sparkline({ values, positive = true }: { values: number[]; positive?: boolean }) {
  const points = values.length > 0 ? values : [0];
  const max = Math.max(...points, 1);
  const coordinates = points
    .map((value, index) => {
      const x = points.length === 1 ? 44 : (index / (points.length - 1)) * 88;
      const y = 25 - (value / max) * 21;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      aria-hidden="true"
      className={positive ? "h-7 w-24 text-success" : "h-7 w-24 text-destructive"}
      viewBox="0 0 88 28"
      fill="none"
      preserveAspectRatio="none"
    >
      <polyline
        points={coordinates}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function TrendBadge({ value, unit = "%" }: { value: number; unit?: "%" | "schools" }) {
  const rounded = unit === "%" ? Math.round(value) : value;
  const positive = rounded >= 0;
  return (
    <span
      className={
        positive
          ? "inline-flex items-center gap-1 font-medium text-success"
          : "inline-flex items-center gap-1 font-medium text-destructive"
      }
    >
      {positive ? (
        <TrendingUp className="size-3.5" aria-hidden="true" />
      ) : (
        <TrendingDown className="size-3.5" aria-hidden="true" />
      )}
      {positive && rounded > 0 ? "+" : ""}
      {rounded}
      {unit === "%" ? "%" : " schools"} this month
    </span>
  );
}

function planLabel(plan: string) {
  return SUBSCRIPTION_TIERS.find((tier) => tier.id === plan)?.label ?? titleCase(plan);
}

function formatLastActive(value: string | null) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Date.now() - date.getTime() < 24 * 60 * 60 * 1000) return "Today";
  return dateFmt(value);
}

function formatRenewal(value: string | null) {
  if (!value) return "Not scheduled";
  return new Date(value).getTime() < Date.now() ? `Overdue · ${dateFmt(value)}` : dateFmt(value);
}

function escapeCsv(value: string | number) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadOverview(data: PlatformOverviewData) {
  const rows: (string | number)[][] = [
    ["Platform overview", `Last ${data.rangeDays} days`],
    ["Metric", "Value"],
    ["Monthly recurring revenue", data.mrr],
    ["Active schools", data.activeSchools],
    ["Active logins (24h)", data.activeLogins24h],
    ["Failed payments", data.failedPayments],
    ["Upcoming renewals", data.upcomingRenewals],
    [],
    ["At-risk school", "Plan", "Students", "Last active", "Renewal", "Status", "Failed payments"],
    ...data.atRiskSchools.map((school) => [
      school.name,
      school.plan,
      school.students,
      school.lastActive ?? "Never",
      school.renewalDate ?? "Not scheduled",
      school.status,
      school.failedPayments,
    ]),
  ];
  const csv = rows.map((row) => row.map(escapeCsv).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `frontline-nexus-platform-overview-${data.rangeDays}d.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  toast.success("Platform overview exported");
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading platform overview">
      <CardsSkeleton count={3} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.9fr)]">
        <div className="fn-panel space-y-5 border border-border/60 p-5">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-[260px] w-full" />
        </div>
        <div className="fn-panel space-y-5 border border-border/60 p-5">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="mx-auto h-48 w-48 rounded-full" />
          <div className="space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
        </div>
      </div>
      <div className="fn-panel space-y-4 border border-border/60 p-5">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    </div>
  );
}

function AtRiskSchoolRow({ school }: { school: AtRiskSchool }) {
  return (
    <TableRow>
      <TableCell>
        <p className="font-medium text-foreground">{school.name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{school.state}</p>
      </TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {planLabel(school.plan)}
      </TableCell>
      <TableCell className="tabular-nums">{numberFmt(school.students)}</TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatLastActive(school.lastActive)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatRenewal(school.renewalDate)}
      </TableCell>
      <TableCell>
        <StatusBadge status={school.status} />
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => toast.info(`Opening renewal tools for ${school.name}`)}
          >
            <CalendarPlus className="size-3.5" aria-hidden="true" />
            Extend trial
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={`Call ${school.name}`}
            onClick={() => toast.info(`Starting a call with ${school.name}`)}
          >
            <Phone className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function PlatformOverview() {
  const [range, setRange] = useState<PlatformOverviewRange>("30d");
  const query = useQuery({
    queryKey: ["platform", "overview", range],
    queryFn: () => getPlatformOverview(range),
    staleTime: 5 * 60 * 1000,
  });
  const data = query.data;

  const revenueData = useMemo(() => {
    const values = data?.mrrTrend ?? [];
    const now = new Date();
    return values.map((value, index) => {
      const month = new Date(now.getFullYear(), now.getMonth() - (values.length - 1 - index), 1);
      return {
        month: month.toLocaleDateString("en-NG", { month: "short" }),
        revenue: value,
      };
    });
  }, [data?.mrrTrend]);

  const statusData = useMemo(
    () =>
      STATUS_META.map((item) => ({
        ...item,
        value: data?.schoolsByStatus[item.status] ?? 0,
      })).filter((item) => item.value > 0),
    [data?.schoolsByStatus],
  );

  const mrrChange = percentageChange(data?.mrrTrend ?? []);
  const activeSchoolsChange = data?.activeSchoolsGrowth ?? 0;

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Platform overview"
          description="A live view of revenue, tenant health and platform activity across every school."
          actions={
            <>
              <Select
                value={range}
                onValueChange={(value) => {
                  if (isPlatformRange(value)) setRange(value);
                }}
              >
                <SelectTrigger className="h-10 w-[142px] bg-card" aria-label="Select date range">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RANGE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                onClick={() => data && downloadOverview(data)}
                disabled={!data}
              >
                {query.isFetching ? (
                  <RefreshCcw className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="size-4" aria-hidden="true" />
                )}
                Export
              </Button>
            </>
          }
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <DashboardSkeleton />
        ) : data ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard
                label="Monthly recurring revenue"
                value={naira(data.mrr)}
                tone="success"
                icon={<WalletCards className="size-5" aria-hidden="true" />}
                hint={
                  <span className="flex items-center justify-between gap-2">
                    <TrendBadge value={mrrChange} />
                    <Sparkline values={data.mrrTrend} positive={mrrChange >= 0} />
                  </span>
                }
              />
              <StatCard
                label="Active schools"
                value={numberFmt(data.activeSchools)}
                icon={<Building2 className="size-5" aria-hidden="true" />}
                hint={
                  <span className="flex items-center justify-between gap-2">
                    <TrendBadge value={activeSchoolsChange} unit="schools" />
                    <Sparkline
                      values={data.activeSchoolsTrend}
                      positive={activeSchoolsChange >= 0}
                    />
                  </span>
                }
              />
              <StatCard
                label="Active logins (24h)"
                value={numberFmt(data.activeLogins24h)}
                icon={<UsersRound className="size-5" aria-hidden="true" />}
                hint="Unique users in the last 24 hours"
              />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.9fr)]">
              <section className="fn-panel min-w-0 border border-border/60 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="font-medium">Revenue</h2>
                    <p className="mt-1 text-sm text-muted-foreground">Last 6 months</p>
                  </div>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success">
                    <Activity className="size-3.5" aria-hidden="true" />
                    Verified payments
                  </span>
                </div>
                <ChartContainer config={REVENUE_CHART_CONFIG} className="mt-5 h-[280px] w-full">
                  <BarChart data={revenueData} margin={{ left: 4, right: 8, top: 8, bottom: 4 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis
                      dataKey="month"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                      dy={10}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                      tickFormatter={(value) => compactNaira(Number(value))}
                      width={54}
                    />
                    <ChartTooltip
                      cursor={{ fill: "var(--muted)" }}
                      content={
                        <ChartTooltipContent
                          formatter={(value) => [naira(Number(value)), "Revenue"]}
                        />
                      }
                    />
                    <Bar
                      dataKey="revenue"
                      fill="var(--color-revenue)"
                      radius={[7, 7, 2, 2]}
                      maxBarSize={42}
                    />
                  </BarChart>
                </ChartContainer>
              </section>

              <section className="fn-panel min-w-0 border border-border/60 p-5">
                <div>
                  <h2 className="font-medium">School status</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Current tenant distribution</p>
                </div>
                {statusData.length > 0 ? (
                  <>
                    <div className="relative mx-auto mt-2 h-[220px] max-w-[280px]">
                      <ChartContainer className="h-full w-full" config={{}}>
                        <PieChart>
                          <Pie
                            data={statusData}
                            dataKey="value"
                            nameKey="label"
                            innerRadius={62}
                            outerRadius={88}
                            paddingAngle={3}
                            strokeWidth={0}
                          >
                            {statusData.map((item) => (
                              <Cell key={item.status} fill={item.color} />
                            ))}
                          </Pie>
                          <ChartTooltip
                            content={
                              <ChartTooltipContent
                                formatter={(value) => [numberFmt(Number(value)), "Schools"]}
                              />
                            }
                          />
                        </PieChart>
                      </ChartContainer>
                      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-2xl font-semibold tabular-nums">
                          {numberFmt(
                            Object.values(data.schoolsByStatus).reduce(
                              (sum, value) => sum + value,
                              0,
                            ),
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground">schools</span>
                      </div>
                    </div>
                    <ul className="mt-1 space-y-2.5">
                      {statusData.map((item) => (
                        <li
                          key={item.status}
                          className="flex items-center justify-between gap-3 text-sm"
                        >
                          <span className="flex items-center gap-2 text-muted-foreground">
                            <span
                              className="size-2.5 rounded-full"
                              style={{ backgroundColor: item.color }}
                              aria-hidden="true"
                            />
                            {item.label}
                          </span>
                          <span className="font-medium tabular-nums">{numberFmt(item.value)}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <div className="flex min-h-[280px] flex-col items-center justify-center gap-2 text-center">
                    <CheckCircle2 className="size-8 text-success" aria-hidden="true" />
                    <p className="font-medium">No tenant data yet</p>
                    <p className="text-sm text-muted-foreground">
                      Schools will appear here as they join.
                    </p>
                  </div>
                )}
              </section>
            </div>

            <section className="fn-panel overflow-hidden border border-border/60">
              <div className="flex flex-wrap items-center justify-between gap-3 p-5">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-medium">Schools needing attention</h2>
                    {data.atRiskSchools.length > 0 ? (
                      <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-semibold text-warning">
                        {data.atRiskSchools.length}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Review renewals, failed payments and inactive accounts.
                  </p>
                </div>
                <Link
                  to="/platform/schools"
                  className="text-sm font-medium text-primary hover:underline"
                >
                  All schools
                </Link>
              </div>
              <div className="border-t border-border/60">
                <Table className="min-w-[900px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>School</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead>Students</TableHead>
                      <TableHead>Last active</TableHead>
                      <TableHead>Renewal</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.atRiskSchools.length > 0 ? (
                      data.atRiskSchools.map((school) => (
                        <AtRiskSchoolRow key={school.id} school={school} />
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={7} className="py-14 text-center">
                          <div className="flex flex-col items-center justify-center gap-2">
                            <CheckCircle2 className="size-8 text-success" aria-hidden="true" />
                            <p className="font-medium">No schools need attention</p>
                            <p className="text-sm text-muted-foreground">
                              Every tenant is in good standing.
                            </p>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </section>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="fn-panel flex items-center gap-3 border border-border/60 p-4">
                <div className="fn-icon-tile size-9 text-info">
                  <CalendarClock className="size-4" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Upcoming renewals</p>
                  <p className="font-semibold tabular-nums">{numberFmt(data.upcomingRenewals)}</p>
                </div>
                <span className="ml-auto text-xs text-muted-foreground">
                  next {data.rangeDays}d
                </span>
              </div>
              <div className="fn-panel flex items-center gap-3 border border-border/60 p-4">
                <div className="fn-icon-tile size-9 text-destructive">
                  <Activity className="size-4" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Failed payments</p>
                  <p className="font-semibold tabular-nums">{numberFmt(data.failedPayments)}</p>
                </div>
                <span className="ml-auto text-xs text-muted-foreground">selected period</span>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </PermissionGate>
  );
}
