import { describe, expect, it } from "vitest";
import {
  naira,
  compactNaira,
  numberFmt,
  percent,
  initials,
  greeting,
  titleCase,
} from "@/lib/format";

describe("naira", () => {
  it("formats zero naira", () => {
    expect(naira(0)).toBe("₦0");
  });

  it("formats thousands without decimals", () => {
    expect(naira(45000)).toMatch("₦45,000");
    expect(naira(1234567)).toMatch("₦1,234,567");
  });
});

describe("compactNaira", () => {
  it("formats millions", () => {
    expect(compactNaira(4200000)).toBe("₦4.2m");
  });

  it("formats thousands", () => {
    expect(compactNaira(25000)).toBe("₦25k");
    expect(compactNaira(1000)).toBe("₦1k");
  });

  it("formats sub-thousands", () => {
    expect(compactNaira(800)).toBe("₦800");
  });
});

describe("numberFmt", () => {
  it("formats with commas", () => {
    expect(numberFmt(1234567)).toBe("1,234,567");
    expect(numberFmt(0)).toBe("0");
  });
});

describe("percent", () => {
  it("rounds and appends %", () => {
    expect(percent(92.4)).toBe("92%");
    expect(percent(100)).toBe("100%");
    expect(percent(0)).toBe("0%");
  });
});

describe("initials", () => {
  it("takes first letters of first two words", () => {
    expect(initials("Aisha Bello")).toBe("AB");
    expect(initials("Ahmed Abubakar Yusuf")).toBe("AA");
  });

  it("handles single name", () => {
    expect(initials("Ahmed")).toBe("A");
  });

  it("upper-cases all initials", () => {
    expect(initials("mrs aisha")).toBe("MA");
  });
});

describe("greeting", () => {
  it("returns morning", () => {
    expect(greeting(new Date(2026, 0, 1, 9, 0))).toBe("Good morning");
  });

  it("returns afternoon", () => {
    expect(greeting(new Date(2026, 0, 1, 14, 0))).toBe("Good afternoon");
  });

  it("returns evening", () => {
    expect(greeting(new Date(2026, 0, 1, 19, 0))).toBe("Good evening");
  });
});

describe("titleCase", () => {
  it("capitalizes words and replaces underscores/hyphens", () => {
    expect(titleCase("school_admin")).toBe("School Admin");
    expect(titleCase("jss-2-a")).toBe("Jss 2 A");
    expect(titleCase("hello world")).toBe("Hello World");
  });
});
