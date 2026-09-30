import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import { toast } from "sonner";
import { naira } from "@/lib/format";
import {
  FEE_TERMS,
  FEE_TYPE_LABELS,
  FEE_TYPES,
  getFeeStructure,
  isDuplicateFee,
  saveLevelFees,
  toTerm,
  toTermValue,
  WHOLE_SESSION,
  type FeeType,
  type LevelFee,
  type LevelFeeStructure,
} from "@/services/finance.service";

/**
 * One card per level, each priced independently. The registration fee gets a
 * dedicated field rather than sitting in the generic list, because every school
 * charges one and because a Nursery family and a Senior Secondary family
 * legitimately pay different amounts.
 *
 * Read access is `finance.read` (a principal can see prices); writes require
 * `finance.structure` (see `canWrite`).
 */
export function PaymentStructurePanel({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["fee-structure"], queryFn: () => getFeeStructure() });

  if (query.isPending) {
    return <p className="text-sm text-muted-foreground">Loading the payment structure…</p>;
  }
  if (query.isError) {
    return (
      <p className="rounded-xl border border-destructive/30 bg-destructive/soft px-4 py-3 text-sm">
        Could not load the payment structure. Reload the page and try again.
      </p>
    );
  }

  const levels = query.data.levels;
  const hasLegacyList = query.data.items.length > 0;
  const anythingPriced = levels.some((level) => level.fees.length > 0);

  return (
    <div className="space-y-4">
      {!anythingPriced && hasLegacyList ? (
        <p
          className="rounded-xl border border-info/30 bg-info-soft px-4 py-3 text-sm"
          role="status"
        >
          You are on a single school-wide fee list, so every student is billed the same. Set a
          figure for each level below to price them separately. Your current list keeps working
          until you do.
        </p>
      ) : null}

      {!anythingPriced && !hasLegacyList ? (
        <p
          className="rounded-xl border border-info/30 bg-info-soft px-4 py-3 text-sm"
          role="status"
        >
          No fees are set yet. Students can still be registered — they stay pending payment until
          you price a level and their invoice is raised.
        </p>
      ) : null}

      {levels.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This school has no levels configured yet, so there is nothing to price. Add classes under
          Academics first.
        </p>
      ) : null}

      {levels.map((level) => (
        <LevelCard
          key={level.id}
          level={level}
          canWrite={canWrite}
          onSaved={() => {
            void queryClient.invalidateQueries({ queryKey: ["fee-structure"] });
            void queryClient.invalidateQueries({ queryKey: ["invoices"] });
            void queryClient.invalidateQueries({ queryKey: ["students"] });
          }}
        />
      ))}
    </div>
  );
}

function LevelCard({
  level,
  canWrite,
  onSaved,
}: {
  level: LevelFeeStructure;
  canWrite: boolean;
  onSaved: () => void;
}) {
  const [rows, setRows] = useState<LevelFee[] | null>(null);
  const fees = rows ?? level.fees;

  // The registration fee is presented on its own, and kept out of the generic
  // list so it cannot be duplicated there or deleted by accident.
  const registration = fees.find((fee) => fee.feeType === "registration") ?? null;
  const otherFees = fees.filter((fee) => fee.feeType !== "registration");
  const total = fees.reduce((sum, fee) => sum + (Number(fee.amount) || 0), 0);

  // The backend rejects blank labels, non-positive amounts and repeated fee
  // types, so mirror that here rather than letting a save fail after the click.
  const valid =
    rows !== null &&
    fees.every(
      (fee) =>
        fee.label.trim() !== "" &&
        Number(fee.amount) > 0 &&
        !isDuplicateFee(fee, fees, fees.indexOf(fee)),
    );

  const save = useMutation({
    mutationFn: () => saveLevelFees(level.id, fees),
    onSuccess: (result) => {
      setRows(null);
      const count = result.invoicedPendingStudents;
      if (count > 0) {
        toast.success(
          `${level.name} fees saved. ${count} student${count === 1 ? "" : "s"} who registered before fees were set up ${count === 1 ? "has" : "have"} now been invoiced.`,
          { description: "They become active once the invoice is paid in full.", duration: 10000 },
        );
      } else {
        toast.success(`${level.name} fees saved.`);
      }
      onSaved();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Could not save the fees.");
    },
  });

  const update = (index: number, patch: Partial<LevelFee>) =>
    setRows(fees.map((fee, i) => (i === index ? { ...fee, ...patch } : fee)));

  /** Registration is a fixed single row, so it is created and cleared in place. */
  const setRegistration = (patch: Partial<LevelFee>) => {
    const next: LevelFee = registration
      ? { ...registration, ...patch }
      : {
          feeType: "registration",
          label: "Registration fee",
          amount: 0,
          term: WHOLE_SESSION,
          isRequired: true,
          ...patch,
        };
    setRows(
      registration
        ? fees.map((fee, i) => (i === fees.indexOf(registration) ? next : fee))
        : [...fees, next],
    );
  };

  const addRow = () =>
    setRows([
      ...fees,
      { feeType: "tuition", label: "", amount: 0, term: WHOLE_SESSION, isRequired: true },
    ]);

  const blank = otherFees.length === 0 && registration === null;

  return (
    <section className="fn-panel p-5" aria-labelledby={`fees-${level.code}`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id={`fees-${level.code}`} className="font-medium">
            {level.name}
          </h3>
          <p className="text-sm text-muted-foreground">
            Billed to every {level.name.toLowerCase()} class in this school.
          </p>
        </div>
        <span className="text-sm font-semibold tabular-nums">
          Total per student: {naira(total)}
        </span>
      </div>

      <div className="mb-4 grid gap-2 rounded-xl border bg-muted/30 p-3 sm:grid-cols-[1fr_9rem]">
        <div>
          <Label htmlFor={`registration-amount-${level.code}`}>Registration fee</Label>
          <Input
            id={`registration-amount-${level.code}`}
            className="mt-1 h-11"
            inputMode="numeric"
            placeholder={naira(0)}
            disabled={!canWrite}
            value={registration?.amount ?? ""}
            onChange={(event) =>
              setRegistration({ amount: Number(event.target.value.replace(/[^0-9]/g, "")) })
            }
          />
        </div>
        <div>
          <Label htmlFor={`registration-term-${level.code}`}>Applies</Label>
          <Select
            value={toTermValue(registration?.term ?? WHOLE_SESSION)}
            disabled={!canWrite}
            onValueChange={(value) => setRegistration({ term: toTerm(value) })}
          >
            <SelectTrigger id={`registration-term-${level.code}`} className="mt-1 h-11">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FEE_TERMS.map((term) => (
                <SelectItem key={term.value} value={term.value}>
                  {term.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {registration ? (
          <p className="text-xs text-muted-foreground sm:col-span-2">
            Charged once when a new {level.name.toLowerCase()} student is admitted, on top of the
            fees below.
          </p>
        ) : null}
      </div>

      {blank ? (
        <p className="mb-3 rounded-lg border p-3 text-sm text-muted-foreground">
          Nothing else is charged to {level.name.toLowerCase()} students yet. Add tuition and any
          other recurring fee below.
        </p>
      ) : null}

      <div className="space-y-2">
        {otherFees.map((fee, index) => {
          const alreadyUsed = isDuplicateFee(fee, otherFees, index);
          return (
            <div
              key={`${fee.feeType}-${fee.term}-${index}`}
              className="grid gap-2 sm:grid-cols-[10rem_1fr_8rem_9rem_auto]"
            >
              <div>
                <Label className="sr-only" htmlFor={`fee-type-${level.code}-${index}`}>
                  Fee type
                </Label>
                <Select
                  value={fee.feeType}
                  disabled={!canWrite}
                  onValueChange={(value) =>
                    update(fees.indexOf(fee), { feeType: value as FeeType })
                  }
                >
                  <SelectTrigger id={`fee-type-${level.code}-${index}`} className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FEE_TYPES.filter((type) => type !== "registration").map((type) => (
                      <SelectItem key={type} value={type}>
                        {FEE_TYPE_LABELS[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="sr-only" htmlFor={`fee-label-${level.code}-${index}`}>
                  Fee label
                </Label>
                <Input
                  id={`fee-label-${level.code}-${index}`}
                  className="h-11"
                  placeholder={FEE_TYPE_LABELS[fee.feeType]}
                  disabled={!canWrite}
                  value={fee.label}
                  onChange={(event) => update(fees.indexOf(fee), { label: event.target.value })}
                />
              </div>

              <div>
                <Label className="sr-only" htmlFor={`fee-amount-${level.code}-${index}`}>
                  Amount
                </Label>
                <Input
                  id={`fee-amount-${level.code}-${index}`}
                  className="h-11"
                  inputMode="numeric"
                  placeholder={naira(0)}
                  aria-invalid={alreadyUsed}
                  disabled={!canWrite}
                  value={fee.amount}
                  onChange={(event) =>
                    update(fees.indexOf(fee), {
                      amount: Number(event.target.value.replace(/[^0-9]/g, "")),
                    })
                  }
                />
              </div>

              <div>
                <Label className="sr-only" htmlFor={`fee-term-${level.code}-${index}`}>
                  Applies
                </Label>
                <Select
                  value={toTermValue(fee.term)}
                  disabled={!canWrite}
                  onValueChange={(value) => update(fees.indexOf(fee), { term: toTerm(value) })}
                >
                  <SelectTrigger id={`fee-term-${level.code}-${index}`} className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FEE_TERMS.map((term) => (
                      <SelectItem key={term.value} value={term.value}>
                        {term.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {canWrite ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-11 text-muted-foreground hover:text-destructive"
                  onClick={() => setRows(fees.filter((row) => row !== fee))}
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                  <span className="sr-only">
                    Remove {fee.label || FEE_TYPE_LABELS[fee.feeType]}
                  </span>
                </Button>
              ) : null}

              {alreadyUsed ? (
                <p className="text-xs text-destructive sm:col-span-5">
                  {FEE_TYPE_LABELS[fee.feeType]} is already set for this term. Each fee type can be
                  entered once per term.
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      {canWrite ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="h-10" onClick={addRow}>
            <Plus className="size-4" aria-hidden="true" />
            Add fee
          </Button>
          <Button
            size="sm"
            className="h-10"
            disabled={rows === null || !valid || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : `Save ${level.name} fees`}
          </Button>
          {rows !== null ? (
            <span className="text-sm text-muted-foreground">Unsaved changes</span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
