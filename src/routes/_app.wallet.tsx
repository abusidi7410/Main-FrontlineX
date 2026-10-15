import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { TablePager } from "@/components/common/table-pager";
import { Button } from "@/components/ui/button";
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
import { dateFmt, dateTimeFmt, naira } from "@/lib/format";
import {
  ACCESS_STATUS_LABEL,
  activateStudent,
  getWallet,
  listStudentAccess,
  listWalletTransactions,
  startDeposit,
  verifyDeposit,
  type StudentAccess,
} from "@/services/wallet.service";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/wallet")({
  head: () => ({
    meta: [
      { title: "Wallet & Billing — Frontline Nexus" },
      {
        name: "description",
        content: "Prepaid wallet, per-student access and transaction history.",
      },
      { property: "og:title", content: "Wallet & Billing — Frontline Nexus" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: WalletPage,
});

const TX_CATEGORIES = [
  "all",
  "deposit",
  "student_activation",
  "student_renewal",
  "refund",
  "adjustment",
] as const;

function accessTone(status: StudentAccess["status"]): string {
  switch (status) {
    case "Active":
      return "active";
    case "ExpiringSoon":
      return "pending";
    case "GracePeriod":
      return "grace";
    case "Expired":
      return "failed";
    case "NeverActivated":
      return "pending";
  }
}

function WalletPage() {
  const queryClient = useQueryClient();
  const walletQuery = useQuery({ queryKey: ["wallet"], queryFn: getWallet });
  const [depositNaira, setDepositNaira] = useState("");
  const [startingDeposit, setStartingDeposit] = useState(false);
  const [depositResult, setDepositResult] = useState<"verifying" | "success" | "failed" | null>(
    null,
  );
  const processedDeposit = useRef<string | null>(null);

  // Handle the Paystack return (?reference=…).
  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const reference = search.get("reference") ?? search.get("trxref");
    if (!reference || processedDeposit.current === reference) return;
    processedDeposit.current = reference;
    setDepositResult("verifying");
    verifyDeposit(reference)
      .then((result) => {
        setDepositResult(result.status);
        if (result.status === "success") {
          void queryClient.invalidateQueries({ queryKey: ["wallet"] });
          void queryClient.invalidateQueries({ queryKey: ["wallet", "transactions"] });
          toast.success("Deposit confirmed. Your wallet has been credited.");
        } else {
          toast.error("The deposit was not completed. Your wallet was not credited.");
        }
      })
      .catch((error: unknown) => {
        setDepositResult("failed");
        toast.error(error instanceof Error ? error.message : "We couldn't verify the deposit.");
      });
  }, [queryClient]);

  const beginDeposit = async () => {
    const nairaAmount = Number(depositNaira);
    if (!Number.isFinite(nairaAmount) || nairaAmount <= 0) {
      toast.error("Enter a deposit amount in naira.");
      return;
    }
    setStartingDeposit(true);
    try {
      const checkout = await startDeposit(Math.round(nairaAmount * 100));
      const destination = new URL(checkout.authorizationUrl);
      if (destination.protocol !== "https:" || destination.hostname !== "checkout.paystack.com") {
        throw new Error("Paystack returned an invalid checkout address.");
      }
      window.location.assign(destination.href);
    } catch (error) {
      setStartingDeposit(false);
      toast.error(error instanceof Error ? error.message : "We couldn't start the deposit.");
    }
  };

  return (
    <PermissionGate permission="finance.payment">
      <div className="space-y-6">
        <PageHeader
          title="Wallet & Billing"
          description="Deposit funds once, then activate students one by one. Money stays in your wallet until a real service charge occurs."
        />

        {depositResult ? (
          <div className="fn-panel space-y-2 p-4" role="status" aria-live="polite">
            <p>
              {depositResult === "verifying" &&
                "Confirming your deposit with the payment provider…"}
              {depositResult === "success" && "Deposit confirmed. Your wallet has been credited."}
              {depositResult === "failed" &&
                "The deposit was not completed. Your wallet was not credited."}
            </p>
          </div>
        ) : null}

        {walletQuery.isError ? (
          <ErrorState onRetry={() => void walletQuery.refetch()} />
        ) : walletQuery.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <WalletBalanceCard
              wallet={walletQuery.data}
              depositNaira={depositNaira}
              setDepositNaira={setDepositNaira}
              startingDeposit={startingDeposit}
              beginDeposit={() => void beginDeposit()}
            />
            <StudentAccessSection wallet={walletQuery.data} />
            <TransactionsSection />
          </>
        )}
      </div>
    </PermissionGate>
  );
}

function WalletBalanceCard({
  wallet,
  depositNaira,
  setDepositNaira,
  startingDeposit,
  beginDeposit,
}: {
  wallet: Awaited<ReturnType<typeof getWallet>>;
  depositNaira: string;
  setDepositNaira: (value: string) => void;
  startingDeposit: boolean;
  beginDeposit: () => void;
}) {
  const accessSummary = useQuery({
    queryKey: ["wallet", "students", "", 1],
    queryFn: () => listStudentAccess(undefined, 1, 1),
  });
  const active = accessSummary.data?.summary.active ?? 0;
  const monthlyBurn = active * wallet.studentPrice;
  const runway =
    monthlyBurn > 0 ? Math.floor(wallet.balance / monthlyBurn) : null;
  return (
    <div className="fn-panel space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Wallet balance</p>
          <p className="font-display text-3xl font-semibold tabular-nums">
            {naira(wallet.balance)}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Student access {naira(wallet.studentPrice)} per student per month ·{" "}
            {active === 0
              ? wallet.balance < wallet.studentPrice
                ? "No active students. Fund your wallet, then activate students one by one."
                : "No active students yet. Your balance covers new activations as you add them."
              : monthlyBurn > wallet.balance
                ? `${active} active · ${naira(monthlyBurn)}/mo renewal cost · balance covers this month only — top up before renewal.`
                : runway !== null && runway > 1
                  ? `${active} active · ${naira(monthlyBurn)}/mo renewal cost · ~${runway} months covered at current usage.`
                  : `${active} active · ${naira(monthlyBurn)}/mo renewal cost · covered for this renewal cycle.`}
            {wallet.autoRenew && active > 0 ? " Renewals run automatically while funded." : ""}
          </p>
        </div>
        <div className="flex w-full max-w-sm flex-col gap-2">
          <Label htmlFor="deposit-amount">Deposit amount (₦)</Label>
          <div className="flex flex-col gap-2 min-[420px]:flex-row">
            <Input
              id="deposit-amount"
              inputMode="decimal"
              placeholder={`Minimum ${naira(wallet.minDeposit)}`}
              value={depositNaira}
              onChange={(e) => setDepositNaira(e.target.value)}
              className="min-w-0 flex-1"
            />
            <Button disabled={startingDeposit} onClick={beginDeposit} className="shrink-0">
              {startingDeposit ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
              {startingDeposit ? "Opening…" : "Fund wallet"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            You decide the amount — no fixed packages. The wallet is credited only after the
            provider confirms payment.
          </p>
        </div>
      </div>
    </div>
  );
}

function StudentAccessSection({ wallet }: { wallet: Awaited<ReturnType<typeof getWallet>> }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["wallet", "students", debounced, page],
    queryFn: () => listStudentAccess(debounced || undefined, page, 20),
    placeholderData: keepPreviousData,
  });

  const activate = async (student: StudentAccess) => {
    setActivatingId(student.studentId);
    try {
      const result = await activateStudent(student.studentId);
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet", "students"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet", "transactions"] });
      setConfirmId(null);
      if (result.created) {
        toast.success(`${student.studentName} activated until ${dateFmt(result.periodEnd)}.`);
      } else {
        toast.info(`${student.studentName} already has paid access. No charge made.`);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Activation failed. No charge was made.",
      );
    } finally {
      setActivatingId(null);
    }
  };

  const rows = list.data?.results ?? [];
  const totalCount = list.data?.count ?? 0;
  const active = list.data?.summary.active ?? 0;
  const needAttention = list.data?.summary.needAttention ?? 0;

  return (
    <section className="space-y-3">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Active paid students" value={String(active)} tone="success" />
        <StatCard
          label="Need activation or renewal"
          value={String(needAttention)}
          tone={needAttention ? "warning" : "success"}
        />
        <StatCard
          label="Access price"
          value={naira(wallet.studentPrice)}
          hint="per student / month"
        />
      </div>

      <div className="fn-panel space-y-3 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="font-medium">Student access</h2>
          <Input
            className="h-10 sm:max-w-xs"
            placeholder="Search by name or admission number"
            aria-label="Search students"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        {list.isError ? (
          <ErrorState onRetry={() => void list.refetch()} />
        ) : list.isPending ? (
          <ListSkeleton />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No students found"
            description="Admit students first — they will appear here for activation."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Student</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Paid through</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.studentId}>
                    <TableCell>
                      <p className="font-medium">{row.studentName}</p>
                      <p className="text-xs text-muted-foreground">{row.admissionNumber}</p>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <StatusBadge status={accessTone(row.status)} />
                        <span className="text-sm">{ACCESS_STATUS_LABEL[row.status]}</span>
                      </span>
                    </TableCell>
                    <TableCell>{row.periodEnd ? dateFmt(row.periodEnd) : "—"}</TableCell>
                    <TableCell className="text-right">
                      {["Active", "ExpiringSoon"].includes(row.status) ? (
                        <span className="text-sm text-muted-foreground">
                          {row.periodEnd ? `Paid to ${dateFmt(row.periodEnd)}` : "Paid"}
                        </span>
                      ) : confirmId === row.studentId ? (
                        <span className="inline-flex flex-col items-end gap-1">
                          <span className="text-xs text-muted-foreground">
                            Charge {naira(wallet.studentPrice)} for one month?
                          </span>
                          <span className="inline-flex gap-2">
                            <Button size="sm" variant="outline" onClick={() => setConfirmId(null)}>
                              Cancel
                            </Button>
                            <Button
                              size="sm"
                              disabled={activatingId !== null}
                              onClick={() => void activate(row)}
                            >
                              {activatingId === row.studentId ? (
                                <Loader2 className="animate-spin" aria-hidden="true" />
                              ) : null}
                              Confirm
                            </Button>
                          </span>
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={activatingId !== null}
                          onClick={() => setConfirmId(row.studentId)}
                        >
                          {row.status === "NeverActivated" ? "Activate" : "Renew"}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePager
              page={page}
              pageSize={list.data?.pageSize ?? 20}
              count={totalCount}
              onPageChange={setPage}
              itemLabel="students"
            />
          </>
        )}
      </div>
    </section>
  );
}

function TransactionsSection() {
  const [category, setCategory] = useState<(typeof TX_CATEGORIES)[number]>("all");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["wallet", "transactions", category, page],
    queryFn: () => listWalletTransactions(page, 20, category === "all" ? undefined : category),
    placeholderData: keepPreviousData,
  });

  return (
    <section className="fn-panel space-y-3 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="font-medium">Transaction history</h2>
        <Select
          value={category}
          onValueChange={(value) => {
            setCategory(value as (typeof TX_CATEGORIES)[number]);
            setPage(1);
          }}
        >
          <SelectTrigger className="sm:w-56" aria-label="Filter by category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TX_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c === "all" ? "All categories" : c.replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : query.data.results.length === 0 ? (
        <EmptyState
          title="No transactions yet"
          description="Deposits, activations, renewals and refunds appear here."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="text-right">Balance after</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.results.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="whitespace-nowrap">{dateTimeFmt(tx.created_at)}</TableCell>
                  <TableCell>
                    <p>{tx.description || tx.reference}</p>
                    <p className="font-mono text-xs text-muted-foreground">{tx.reference}</p>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={tx.status} />
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums font-medium",
                      tx.direction === "credit" ? "text-success" : "text-foreground",
                    )}
                  >
                    {tx.direction === "credit" ? "+" : "−"}
                    {naira(tx.amount_kobo / 100)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {naira(tx.balance_after_kobo / 100)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePager
            page={query.data.page}
            pageSize={query.data.pageSize}
            count={query.data.count}
            onPageChange={setPage}
            itemLabel="transactions"
          />
        </>
      )}
    </section>
  );
}
