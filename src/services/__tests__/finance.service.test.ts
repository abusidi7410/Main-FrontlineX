import { describe, expect, it } from "vitest";
import {
  ALL_TERMS,
  FEE_TERMS,
  FEE_TYPES,
  isDuplicateFee,
  toTerm,
  toTermValue,
  WHOLE_SESSION,
  type LevelFee,
} from "@/services/finance.service";

/** `exactOptionalPropertyTypes` is on, so the merge is asserted once here. */
const fee = (over: Partial<LevelFee> = {}): LevelFee =>
  ({
    feeType: "tuition",
    label: "Tuition",
    amount: 40000,
    term: WHOLE_SESSION,
    isRequired: true,
    ...over,
  }) as LevelFee;

describe("term encoding", () => {
  it("stores a whole-session fee as a blank term", () => {
    expect(WHOLE_SESSION).toBe("");
    expect(toTerm(ALL_TERMS)).toBe("");
  });

  it("round-trips a named term", () => {
    expect(toTerm("First Term")).toBe("First Term");
    expect(toTermValue("First Term")).toBe("First Term");
  });

  it("round-trips the whole-session option", () => {
    expect(toTermValue(WHOLE_SESSION)).toBe(ALL_TERMS);
    expect(toTerm(toTermValue(WHOLE_SESSION))).toBe(WHOLE_SESSION);
  });

  it("never offers an empty Select value, which Radix rejects", () => {
    expect(FEE_TERMS.every((term) => term.value.length > 0)).toBe(true);
  });
});

describe("isDuplicateFee", () => {
  /** `ignoreIndex` is the row's own index in `rows`, so it never matches itself. */
  const dupesWith = (rows: LevelFee[], index: number) =>
    isDuplicateFee(rows[index] as LevelFee, rows, index);

  it("flags the same fee type in the same term", () => {
    const rows = [
      fee(),
      fee({ label: "Bus fare", feeType: "transport" }),
      fee({ feeType: "transport" }),
    ];
    expect(dupesWith(rows, 2)).toBe(true);
  });

  it("allows the same fee type in different terms", () => {
    const rows = [fee({ term: "First Term" }), fee({ term: "Second Term" })];
    expect(dupesWith(rows, 1)).toBe(false);
  });

  it("allows different fee types in the same term", () => {
    const rows = [fee(), fee({ feeType: "transport" })];
    expect(dupesWith(rows, 1)).toBe(false);
  });

  it("does not treat a row as a duplicate of itself", () => {
    const rows = [fee()];
    expect(dupesWith(rows, 0)).toBe(false);
  });
});

describe("FEE_TYPES", () => {
  it("includes a registration type, which the editor gives a dedicated field", () => {
    expect(FEE_TYPES).toContain("registration");
  });
});
