import { describe, expect, it } from "vitest";
import {
  SUBSCRIPTION_TIERS,
  GROWTH_ALLOWANCE_RATIO,
  tierById,
  tierForStudentCount,
} from "@/constants/plans";

describe("tierById", () => {
  it("returns the matching tier", () => {
    const tier = tierById("t600");
    expect(tier.id).toBe("t600");
    expect(tier.label).toBe("401 – 600 students");
    expect(tier.monthlyPrice).toBe(25000);
  });

  it("falls back to first tier for unknown id", () => {
    const tier = tierById("nonexistent");
    expect(tier.id).toBe("t100");
  });
});

describe("tierForStudentCount", () => {
  it("returns t100 for count in range", () => {
    expect(tierForStudentCount(1).id).toBe("t100");
    expect(tierForStudentCount(100).id).toBe("t100");
  });

  it("returns t200 for 101-200", () => {
    expect(tierForStudentCount(150).id).toBe("t200");
  });

  it("returns t400 for 201-400", () => {
    expect(tierForStudentCount(300).id).toBe("t400");
  });

  it("returns t600 for 401-600", () => {
    expect(tierForStudentCount(523).id).toBe("t600");
  });

  it("returns tmax for counts above highest bracket", () => {
    expect(tierForStudentCount(2500).id).toBe("tmax");
    expect(tierForStudentCount(2001).id).toBe("tmax");
  });

  it("returns first tier for count 0", () => {
    expect(tierForStudentCount(0).id).toBe("t100");
  });

  it("tier boundaries are contiguous", () => {
    const sorted = [...SUBSCRIPTION_TIERS].sort((a, b) => a.minStudents - b.minStudents);
    for (let i = 0; i < sorted.length; i++) {
      const t = sorted[i]!;
      expect(tierForStudentCount(t.minStudents).id).toBe(t.id);
    }
  });
});

describe("GROWTH_ALLOWANCE_RATIO", () => {
  it("is 7.5%", () => {
    expect(GROWTH_ALLOWANCE_RATIO).toBe(0.075);
  });
});

describe("SUBSCRIPTION_TIERS", () => {
  it("is ordered by minStudents ascending", () => {
    for (let i = 1; i < SUBSCRIPTION_TIERS.length; i++) {
      expect(SUBSCRIPTION_TIERS[i]!.minStudents).toBeGreaterThan(
        SUBSCRIPTION_TIERS[i - 1]!.minStudents,
      );
    }
  });

  it("all tiers have required fields", () => {
    for (const tier of SUBSCRIPTION_TIERS) {
      expect(tier.id).toBeTruthy();
      expect(tier.monthlyPrice).toBeGreaterThan(0);
      expect(tier.aiCredits).toBeGreaterThan(0);
      expect(tier.features.length).toBeGreaterThan(0);
    }
  });
});
