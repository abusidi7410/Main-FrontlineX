import { useQuery } from "@tanstack/react-query";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { useAuthenticatedSession } from "@/auth/session";
import { compactNaira, dateTimeFmt, greeting, naira, titleCase } from "@/lib/format";
import { listInvoices, listPayments } from "@/services/finance.service";

export function AccountantDashboard() {
  const { user, school } = useAuthenticatedSession();
  const invoices = useQuery({ queryKey: ["invoices", ""], queryFn: () => listInvoices() });
  const payments = useQuery({ queryKey: ["payments"], queryFn: listPayments });

  if (invoices.isError || payments.isError) {
    return (
      <ErrorState onRetry={() => void Promise.all([invoices.refetch(), payments.refetch()])} />
    );
  }

  const outstanding = invoices.data?.reduce((sum, i) => sum + (i.total - i.paid), 0) ?? 0;
  const verified = payments.data?.filter((p) => p.status === "verified") ?? [];
  const todayTotal = verified
    .filter((p) => new Date(p.createdAt).toDateString() === new Date().toDateString())
    .reduce((sum, p) => sum + p.amount, 0);
  const pending = payments.data?.filter((p) => p.status === "pending") ?? [];
  const cashBalance = verified
    .filter((p) => p.method === "cash")
    .reduce((sum, p) => sum + p.amount, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="mt-1 text-muted-foreground">
          {school?.name} · {school?.currentTerm}
        </p>
      </div>

      {invoices.isPending || payments.isPending ? (
        <CardsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Collected today"
            value={compactNaira(todayTotal)}
            tone="success"
            hint="Verified payments"
          />
          <StatCard
            label="Outstanding fees"
            value={compactNaira(outstanding)}
            tone="warning"
            hint="Current term invoices"
          />
          <StatCard
            label="Awaiting verification"
            value={pending.length}
            hint="Bank transfers and online payments"
          />
          <StatCard
            label="Cash recorded"
            value={compactNaira(cashBalance)}
            hint="To reconcile at close of day"
          />
        </div>
      )}

      <QuickActions
        actions={[
          { label: "Record payment", to: "/finance", icon: "wallet" },
          { label: "Verify transfer", to: "/finance", icon: "receipt" },
          { label: "View invoices", to: "/finance/invoices", icon: "receipt" },
          { label: "Student balances", to: "/students", icon: "users" },
          { label: "Financial reports", to: "/reports", icon: "chart" },
          { label: "AI assistant", to: "/ai", icon: "sparkles" },
        ]}
      />

      <section className="fn-panel overflow-hidden" aria-labelledby="recent-heading">
        <div className="border-b px-5 py-4">
          <h2 id="recent-heading" className="font-semibold">
            Recent transactions
          </h2>
        </div>
        {payments.data && payments.data.length > 0 ? (
          <ul className="divide-y">
            {payments.data.slice(0, 6).map((payment) => (
              <li
                key={payment.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{payment.studentName}</p>
                  <p className="text-sm text-muted-foreground">
                    {titleCase(payment.method)} · {payment.reference} ·{" "}
                    {dateTimeFmt(payment.createdAt)}
                  </p>
                </div>
                <p className="font-medium tabular-nums">{naira(payment.amount)}</p>
                <StatusBadge status={payment.status} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-center text-muted-foreground">
            No payments recorded yet. Record your first payment from the Payments page.
          </p>
        )}
      </section>
    </div>
  );
}
