import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Download, Printer, RotateCcw, Search, Settings2, XCircle } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { TablePager } from "@/components/common/table-pager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError, downloadBlob } from "@/api/client";
import { useSession } from "@/auth/session";
import { useDebounced } from "@/hooks/use-debounced";
import { dateTimeFmt, naira } from "@/lib/format";
import {
  downloadReceiptPdf,
  getReceiptSettings,
  getReceiptStats,
  listReceipts,
  reprintReceipt,
  updateReceiptSettings,
  voidReceipt,
} from "@/services/receipts.service";
import type { Receipt, ReceiptSettings, ReceiptStatus } from "@/types";

export const Route = createFileRoute("/_app/finance/receipts")({
  head: () => ({
    meta: [
      { title: "Receipts — Frontline Nexus" },
      {
        name: "description",
        content: "Find, reprint and void official school-fee receipts.",
      },
      { property: "og:title", content: "Receipts — Frontline Nexus" },
      {
        property: "og:description",
        content: "Find, reprint and void official school-fee receipts.",
      },
      { property: "robots", content: "noindex" },
    ],
  }),
  component: ReceiptsPage,
});

const TABS: { value: ReceiptStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "issued", label: "Issued" },
  { value: "voided", label: "Voided" },
];

function fileSafe(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, "-");
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiRequestError ? error.message : fallback;
}

function ReceiptsPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<ReceiptStatus | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [voiding, setVoiding] = useState<Receipt | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const debouncedSearch = useDebounced(search);

  const canSettings = can("receipts.settings");
  const stats = useQuery({ queryKey: ["receipt-stats"], queryFn: getReceiptStats });
  const receipts = useQuery({
    queryKey: ["receipts", debouncedSearch, tab, page],
    queryFn: () => listReceipts({ search: debouncedSearch, status: tab, page, pageSize: 25 }),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["receipts"] });
    await queryClient.invalidateQueries({ queryKey: ["receipt-stats"] });
  };

  const download = useMutation({
    mutationFn: async (receipt: Receipt) => ({
      receipt,
      blob: await downloadReceiptPdf(receipt.id),
    }),
    onSuccess: ({ receipt, blob }) => downloadBlob(blob, `${fileSafe(receipt.receiptNumber)}.pdf`),
    onError: (error) => toast.error(errorText(error, "That receipt could not be downloaded.")),
  });

  const reprint = useMutation({
    mutationFn: (receipt: Receipt) => reprintReceipt(receipt.id),
    onSuccess: async (receipt) => {
      toast.success(`Reprint recorded (${receipt.reprintCount} total).`);
      download.mutate(receipt);
      await refresh();
    },
    onError: (error) => toast.error(errorText(error, "That reprint failed.")),
  });

  const remove = useMutation({
    mutationFn: (input: { receipt: Receipt; reason: string }) =>
      voidReceipt(input.receipt.id, input.reason),
    onSuccess: async () => {
      toast.success("Receipt voided. The payment itself was not changed.");
      setVoiding(null);
      setVoidReason("");
      await refresh();
    },
    onError: (error) => toast.error(errorText(error, "That receipt could not be voided.")),
  });

  return (
    <PermissionGate permission="receipts.read">
      <div className="space-y-6">
        <PageHeader
          title="Receipts"
          description="Official, numbered receipts for verified fee payments. Reprints are logged; voided receipts stay on file."
          actions={
            canSettings ? (
              <Button variant="outline" className="h-11" onClick={() => setSettingsOpen(true)}>
                <Settings2 className="size-4" aria-hidden="true" />
                Receipt settings
              </Button>
            ) : null
          }
        />

        {stats.data ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Receipts issued"
              value={stats.data.totalIssued}
              icon={<Printer className="size-5" aria-hidden="true" />}
            />
            <StatCard
              label="This month"
              value={stats.data.issuedThisMonth}
              tone="success"
              hint={`${naira(Number(stats.data.valueThisMonth) || 0)} receipted`}
            />
            <StatCard
              label="Value this month"
              value={naira(Number(stats.data.valueThisMonth) || 0)}
              hint="Verified payments receipted"
            />
            <StatCard
              label="Voided"
              value={stats.data.totalVoided}
              tone={stats.data.totalVoided > 0 ? "warning" : "default"}
              hint="Still visible for audit"
            />
          </div>
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Tabs
            value={tab || "all"}
            onValueChange={(value) => {
              setTab(value === "all" ? "" : (value as ReceiptStatus));
              setPage(1);
            }}
          >
            <TabsList>
              {TABS.map((item) => (
                <TabsTrigger key={item.value || "all"} value={item.value || "all"}>
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className="relative sm:w-72">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search number, student or payer"
              aria-label="Search receipts"
              className="h-11 pl-9"
            />
          </div>
        </div>

        {receipts.isError ? (
          <ErrorState onRetry={() => void receipts.refetch()} />
        ) : receipts.isPending ? (
          <ListSkeleton />
        ) : receipts.data.results.length === 0 ? (
          <EmptyState
            title="No receipts yet"
            description={
              search
                ? "No receipt matches that search. Try a receipt number, student name or payer."
                : "Issue a receipt from a verified payment on the Payments page and it will appear here."
            }
          />
        ) : (
          <ul className="fn-panel divide-y">
            {receipts.data.results.map((receipt) => (
              <li key={receipt.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {receipt.receiptNumber}
                    {receipt.replacesId ? (
                      <span className="ml-2 text-sm font-normal text-muted-foreground">
                        (replacement)
                      </span>
                    ) : null}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {receipt.studentName || receipt.payerName}
                    {receipt.admissionNumber ? ` · ${receipt.admissionNumber}` : ""} ·{" "}
                    {dateTimeFmt(receipt.issuedAt)} · by {receipt.issuedBy}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {receipt.purpose}
                    {receipt.reprintCount > 0
                      ? ` · reprinted ${receipt.reprintCount}×${
                          receipt.lastReprintedAt
                            ? ` (last ${dateTimeFmt(receipt.lastReprintedAt)})`
                            : ""
                        }`
                      : ""}
                  </p>
                  {receipt.status === "voided" ? (
                    <p className="text-sm text-destructive">
                      Voided{receipt.voidedAt ? ` ${dateTimeFmt(receipt.voidedAt)}` : ""}
                      {receipt.voidReason ? ` — ${receipt.voidReason}` : ""}
                    </p>
                  ) : null}
                </div>
                <div className="text-right">
                  <p className="font-medium tabular-nums">{naira(Number(receipt.amount) || 0)}</p>
                  <p className="text-sm text-muted-foreground">
                    Balance {naira(Number(receipt.balanceAfter) || 0)}
                  </p>
                </div>
                <StatusBadge status={receipt.status} />
                <Button
                  variant="outline"
                  className="h-11"
                  disabled={download.isPending}
                  onClick={() => download.mutate(receipt)}
                >
                  <Download className="size-4" aria-hidden="true" />
                  PDF
                </Button>
                {receipt.status === "issued" && can("receipts.reprint") ? (
                  <Button
                    variant="ghost"
                    className="h-11"
                    disabled={reprint.isPending}
                    onClick={() => reprint.mutate(receipt)}
                  >
                    <RotateCcw className="size-4" aria-hidden="true" />
                    Reprint
                  </Button>
                ) : null}
                {receipt.status === "issued" && can("receipts.void") ? (
                  <Button
                    variant="ghost"
                    className="h-11 text-destructive"
                    onClick={() => {
                      setVoiding(receipt);
                      setVoidReason("");
                    }}
                  >
                    <XCircle className="size-4" aria-hidden="true" />
                    Void
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {receipts.data ? (
          <TablePager
            page={receipts.data.page}
            pageSize={receipts.data.pageSize}
            count={receipts.data.count}
            onPageChange={setPage}
            itemLabel="receipts"
            disabled={receipts.isFetching}
          />
        ) : null}
      </div>

      <Dialog open={voiding !== null} onOpenChange={(open) => !open && setVoiding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Void {voiding?.receiptNumber}?</DialogTitle>
            <DialogDescription>
              The receipt stays on file marked void. The payment and invoice are not changed. If
              money was received, issue a replacement receipt instead of leaving the family without
              one.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="voidReason">Reason</Label>
            <Textarea
              id="voidReason"
              rows={3}
              value={voidReason}
              onChange={(event) => setVoidReason(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVoiding(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending || voidReason.trim() === ""}
              onClick={() => {
                if (voiding) remove.mutate({ receipt: voiding, reason: voidReason.trim() });
              }}
            >
              Void receipt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {canSettings ? (
        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Receipt settings</DialogTitle>
              <DialogDescription>
                These apply to receipts issued from now on. Receipts already issued keep their
                snapshot.
              </DialogDescription>
            </DialogHeader>
            {settingsOpen ? <ReceiptSettingsForm onClose={() => setSettingsOpen(false)} /> : null}
          </DialogContent>
        </Dialog>
      ) : null}
    </PermissionGate>
  );
}

function ReceiptSettingsForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["receipt-settings"], queryFn: getReceiptSettings });

  if (settings.isError) {
    return (
      <ErrorState
        message="We couldn't load the receipt settings."
        onRetry={() => void settings.refetch()}
      />
    );
  }
  if (settings.isPending || !settings.data) return <ListSkeleton rows={3} />;

  return (
    <ReceiptSettingsFields
      settings={settings.data}
      onClose={onClose}
      onSaved={async (updated) => {
        queryClient.setQueryData(["receipt-settings"], updated);
        toast.success("Receipt settings saved.");
        onClose();
      }}
    />
  );
}

function ReceiptSettingsFields({
  settings,
  onSaved,
  onClose,
}: {
  settings: ReceiptSettings;
  onSaved: (updated: ReceiptSettings) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<ReceiptSettings>(settings);
  const [prefixError, setPrefixError] = useState("");

  const save = useMutation({
    mutationFn: (input: Partial<ReceiptSettings>) => updateReceiptSettings(input),
    onSuccess: onSaved,
    onError: (error) => {
      if (error instanceof ApiRequestError && error.fieldErrors?.["prefix"]) {
        setPrefixError(error.fieldErrors["prefix"]);
        return;
      }
      toast.error(errorText(error, "We couldn't save the receipt settings."));
    },
  });

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!form.prefix.trim()) {
          setPrefixError("Enter a receipt prefix.");
          return;
        }
        setPrefixError("");
        save.mutate(form);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="prefix">Number prefix</Label>
          <Input
            id="prefix"
            className="h-12 uppercase"
            value={form.prefix}
            onChange={(event) => {
              setForm((current) => ({ ...current, prefix: event.target.value }));
              setPrefixError("");
            }}
          />
          {prefixError ? (
            <p role="alert" className="text-sm text-destructive">
              {prefixError}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Letters and digits, e.g. RCP. The school code and year are added automatically.
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="paperSize">Paper size</Label>
          <Select
            value={form.paperSize}
            onValueChange={(value) =>
              setForm((current) => ({
                ...current,
                paperSize: value as ReceiptSettings["paperSize"],
              }))
            }
          >
            <SelectTrigger id="paperSize" className="h-12">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="A5">A5 (receipt)</SelectItem>
              <SelectItem value="A4">A4 (full page)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="footerNote">Footer note</Label>
        <Input
          id="footerNote"
          className="h-12"
          maxLength={255}
          value={form.footerNote}
          onChange={(event) =>
            setForm((current) => ({ ...current, footerNote: event.target.value }))
          }
        />
      </div>
      <div className="flex items-center justify-between gap-4 rounded-xl border p-3">
        <div>
          <Label htmlFor="showLogo" className="cursor-pointer">
            Show school logo
          </Label>
          <p className="text-sm text-muted-foreground">
            Only printed when your school logo is available to the server.
          </p>
        </div>
        <Switch
          id="showLogo"
          checked={form.showLogo}
          onCheckedChange={(checked) => setForm((current) => ({ ...current, showLogo: checked }))}
        />
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save settings"}
        </Button>
      </DialogFooter>
    </form>
  );
}
