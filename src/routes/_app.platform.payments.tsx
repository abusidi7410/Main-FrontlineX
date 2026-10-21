import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { TablePager } from "@/components/common/table-pager";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebounced } from "@/hooks/use-debounced";
import { dateTimeFmt, naira, numberFmt } from "@/lib/format";
import {
  createManualAdjustment,
  getSchoolMessaging,
  listAllPlatformSchools,
  listPlatformTransactions,
  listSubscriptionPayments,
} from "@/services/platform.service";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/platform/payments")({
  head: () => ({
    meta: [
      { title: "Payments & Revenue — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Verified subscription payments and revenue across every school.",
      },
      { property: "og:title", content: "Payments & Revenue — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformPaymentsPage,
});

const STATUSES = ["all", "success", "pending", "failed", "abandoned"] as const;

const TXN_CATEGORIES = [
  "all",
  "deposit",
  "student_activation",
  "student_renewal",
  "sms_alert",
  "refund",
  "adjustment",
] as const;

const TXN_DIRECTIONS = ["all", "credit", "debit"] as const;

function PlatformPaymentsPage() {
  const [tab, setTab] = useState<"subscriptions" | "wallets">("wallets");
  const [fundOpen, setFundOpen] = useState(false);

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Payments & Revenue"
          description="All money movement on the platform: school wallet fundings and charges, plus subscription gateway payments."
          actions={<Button onClick={() => setFundOpen(true)}>Fund school wallet</Button>}
        />

        <div className="flex gap-2" role="tablist" aria-label="Payment views">
          {(
            [
              { id: "wallets", label: "Wallet transactions" },
              { id: "subscriptions", label: "Subscription payments" },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={
                tab === t.id
                  ? "min-h-11 rounded-full border border-primary bg-primary-soft px-4 font-medium text-primary"
                  : "min-h-11 rounded-full border bg-surface px-4 font-medium hover:bg-muted"
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "wallets" ? <WalletTransactionsSection /> : <SubscriptionSection />}

        <FundWalletDialog open={fundOpen} onOpenChange={setFundOpen} />
      </div>
    </PermissionGate>
  );
}

/**
 * Platform-only manual funding: pick any school, credit its wallet and record
 * a required reason. The backend writes a `wallet.adjustment` audit entry with
 * before/after values, so this dialog never hides the money trail.
 */
function FundWalletDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [schoolId, setSchoolId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);

  const schoolsQuery = useQuery({
    queryKey: ["platform", "schools", "all"],
    queryFn: () => listAllPlatformSchools(),
    enabled: open,
  });

  const balanceQuery = useQuery({
    queryKey: ["platform", "school", schoolId, "messaging"],
    queryFn: () => getSchoolMessaging(schoolId),
    enabled: open && schoolId !== "",
  });

  const selectedSchool = schoolsQuery.data?.find((school) => school.id === schoolId);
  const amountKobo = Math.round((Number(amount) || 0) * 100);
  const balanceKobo = balanceQuery.data?.balanceKobo;

  const fund = useMutation({
    mutationFn: () => createManualAdjustment({ schoolId, amountKobo, reason: reason.trim() }),
    onSuccess: (result) => {
      toast.success(
        `${selectedSchool?.name ?? "School"} wallet funded. New balance ${naira(
          result.balanceKobo / 100,
        )}.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["platform", "wallet-transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
      void queryClient.invalidateQueries({ queryKey: ["platform", "dashboard"] });
      setSchoolId("");
      setAmount("");
      setReason("");
      setConfirming(false);
      onOpenChange(false);
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "We couldn't fund that wallet."),
  });

  useEffect(() => {
    if (!open) {
      setSchoolId("");
      setAmount("");
      setReason("");
      setConfirming(false);
    }
  }, [open]);

  const invalid = !schoolId || !reason.trim() || !Number.isFinite(amountKobo) || amountKobo <= 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!fund.isPending) onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Fund a school wallet</DialogTitle>
          <DialogDescription>
            Manually credit any school&apos;s prepaid wallet. A written reason is required and every
            funding is written to the audit log.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="fund-school">School</Label>
            <Select
              value={schoolId}
              onValueChange={(value) => {
                setSchoolId(value);
                setConfirming(false);
              }}
              disabled={schoolsQuery.isPending}
            >
              <SelectTrigger id="fund-school" className="h-11">
                <SelectValue
                  placeholder={
                    schoolsQuery.isPending ? "Loading schools…" : "Choose a school to fund"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {(schoolsQuery.data ?? []).map((school) => (
                  <SelectItem key={school.id} value={school.id}>
                    {school.name}
                    {school.state ? ` — ${school.state}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {schoolsQuery.isError ? (
              <p className="text-sm text-destructive">
                We couldn&apos;t load schools. Close and try again.
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="fund-amount">Amount (₦)</Label>
            <Input
              id="fund-amount"
              className="h-11"
              inputMode="decimal"
              placeholder="e.g. 25000"
              value={amount}
              onChange={(event) => {
                setAmount(event.target.value);
                setConfirming(false);
              }}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="fund-reason">Reason (required)</Label>
            <Input
              id="fund-reason"
              className="h-11"
              placeholder="e.g. Bank transfer received — GTBank ref 1234"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setConfirming(false);
              }}
            />
          </div>

          {schoolId && !Number.isNaN(amountKobo) && amountKobo > 0 ? (
            <div className="rounded-lg border border-border/60 bg-muted/40 p-3 text-sm">
              <p className="font-medium">
                {selectedSchool?.name ?? "Selected school"} · +{naira(amountKobo / 100)}
              </p>
              <p className="mt-1 text-muted-foreground">
                {typeof balanceKobo === "number"
                  ? `Balance ${naira(balanceKobo / 100)} → ${naira(
                      (balanceKobo + amountKobo) / 100,
                    )} after funding.`
                  : "Loading current balance…"}
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          {confirming ? (
            <>
              <Button
                variant="ghost"
                onClick={() => setConfirming(false)}
                disabled={fund.isPending}
              >
                Back
              </Button>
              <Button onClick={() => fund.mutate()} disabled={fund.isPending}>
                {fund.isPending ? "Funding…" : `Confirm ${naira(amountKobo / 100)}`}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={() => setConfirming(true)} disabled={invalid}>
                Review funding
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SubscriptionSection() {
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("all");
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);

  const query = useQuery({
    queryKey: ["platform", "payments", status, debounced],
    queryFn: () =>
      listSubscriptionPayments({
        status: status === "all" ? "" : status,
        search: debounced,
      }),
  });

  const payments = query.data ?? [];
  const verified = payments.filter((p) => p.status === "success");
  const revenue = verified.reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const pending = payments.filter((p) => p.status === "pending").length;
  const failed = payments.filter((p) => p.status === "failed").length;

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Every subscription payment attempt. Only verified gateway payments count as revenue —
        complimentary access is never recorded here.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Verified revenue (filter)"
          value={naira(Math.round(revenue))}
          tone="success"
        />
        <StatCard label="Successful payments" value={numberFmt(verified.length)} tone="success" />
        <StatCard
          label="Pending payments"
          value={numberFmt(pending)}
          tone={pending ? "warning" : "success"}
        />
        <StatCard
          label="Failed payments"
          value={numberFmt(failed)}
          tone={failed ? "danger" : "success"}
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          className="h-11"
          placeholder="Search by reference or school name"
          aria-label="Search payments"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={status} onValueChange={(v) => setStatus(v as (typeof STATUSES)[number])}>
          <SelectTrigger className="h-11 sm:w-56" aria-label="Filter by payment status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "all" ? "All statuses" : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : payments.length === 0 ? (
        <EmptyState
          title="No payments match"
          description="Try a different reference, school name or status."
        />
      ) : (
        <div className="fn-panel overflow-x-auto">
          <Table className="min-w-[860px]">
            <TableHeader>
              <TableRow>
                <TableHead>Reference</TableHead>
                <TableHead>School</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Purpose</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Paid</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-xs">{p.reference}</TableCell>
                  <TableCell className="font-medium">{p.schoolName}</TableCell>
                  <TableCell className="text-muted-foreground">{p.planName || "—"}</TableCell>
                  <TableCell className="tabular-nums">{naira(Number(p.amount) || 0)}</TableCell>
                  <TableCell className="text-muted-foreground">{p.purpose}</TableCell>
                  <TableCell>
                    <StatusBadge
                      status={
                        p.status === "success"
                          ? "active"
                          : p.status === "pending"
                            ? "pending"
                            : "failed"
                      }
                    />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {p.paidAt ? dateTimeFmt(p.paidAt) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function WalletTransactionsSection() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<(typeof TXN_CATEGORIES)[number]>("all");
  const [direction, setDirection] = useState<(typeof TXN_DIRECTIONS)[number]>("all");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search, 300);
  const query = useQuery({
    queryKey: ["platform", "wallet-transactions", debounced, category, direction, page],
    queryFn: () =>
      listPlatformTransactions({
        ...(debounced ? { search: debounced } : {}),
        ...(category === "all" ? {} : { category }),
        ...(direction === "all" ? {} : { direction }),
        page,
        pageSize: 20,
      }),
    placeholderData: keepPreviousData,
  });
  const summary = query.data?.summary;
  const rows = query.data?.results ?? [];

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Every wallet movement across all schools — deposits in, access charges, renewals, refunds
        and manual adjustments. Totals reflect the current filters, not just this page.
      </p>

      {summary ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Deposits in (filter)"
            value={`+${naira(summary.creditsKobo / 100)}`}
            tone="success"
          />
          <StatCard label="Charges out (filter)" value={`−${naira(summary.debitsKobo / 100)}`} />
          <StatCard label="Transactions (filter)" value={numberFmt(summary.count)} />
        </div>
      ) : null}

      <div className="flex flex-col gap-3 lg:flex-row">
        <Input
          className="h-11 lg:max-w-xs"
          placeholder="Search reference, school or description"
          aria-label="Search wallet transactions"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <Select
          value={category}
          onValueChange={(v) => {
            setCategory(v as (typeof TXN_CATEGORIES)[number]);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-11 lg:w-52" aria-label="Filter by category">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            {TXN_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c === "all" ? "All categories" : c.replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={direction}
          onValueChange={(v) => {
            setDirection(v as (typeof TXN_DIRECTIONS)[number]);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-11 lg:w-44" aria-label="Filter by direction">
            <SelectValue placeholder="In and out" />
          </SelectTrigger>
          <SelectContent>
            {TXN_DIRECTIONS.map((d) => (
              <SelectItem key={d} value={d}>
                {d === "all" ? "In and out" : d === "credit" ? "Money in" : "Money out"}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No transactions match"
          description="Try a different reference, school, category or direction."
        />
      ) : (
        <>
          <div className="fn-panel overflow-x-auto">
            <Table className="min-w-[920px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>School</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="text-right">Student</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {dateTimeFmt(tx.created_at)}
                    </TableCell>
                    <TableCell className="font-medium">{tx.schoolName || "—"}</TableCell>
                    <TableCell>
                      <p>{tx.description || tx.reference}</p>
                      <p className="font-mono text-xs text-muted-foreground">{tx.reference}</p>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={tx.status} />
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right font-medium tabular-nums",
                        tx.direction === "credit" ? "text-success" : "text-foreground",
                      )}
                    >
                      {tx.direction === "credit" ? "+" : "−"}
                      {naira(tx.amount_kobo / 100)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {tx.studentName || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <TablePager
            page={query.data?.page ?? page}
            pageSize={query.data?.pageSize ?? 20}
            count={query.data?.count ?? 0}
            onPageChange={setPage}
            itemLabel="transactions"
          />
        </>
      )}
    </div>
  );
}
