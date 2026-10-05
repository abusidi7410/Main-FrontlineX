import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Responsive layout contracts.
 *
 * These are structural assertions on the source rather than rendered-output
 * assertions, because the project has no component-test setup (every existing
 * test is service or pure-logic) and these screens need router, query and
 * permission providers to mount. The invariants are cheap to state and easy to
 * break by accident, so they are pinned here.
 *
 * Each case is a bug that was actually present:
 *  - a vertically centred dialog with no max-height or scroll is clipped at
 *    BOTH ends on a phone, leaving the middle of the form unreachable;
 *  - a table wider than the viewport is technically scrollable, but on a phone
 *    it means scrolling sideways past most of the columns to reach an action.
 */

const read = (relative: string) => readFileSync(resolve(process.cwd(), "src", relative), "utf8");

describe("dialogs fit a small screen", () => {
  const source = read("components/ui/dialog.tsx");

  it("caps its height and scrolls", () => {
    // `dvh` rather than `vh`: mobile browser chrome changes the visible height,
    // and `vh` overshoots it, pushing the footer below the fold.
    expect(source).toContain("max-h-[90dvh]");
    expect(source).toContain("overflow-y-auto");
  });

  it("keeps a gutter so the panel is never flush to the screen edges", () => {
    expect(source).toContain("w-[calc(100%-2rem)]");
  });

  it("reduces its padding on a phone", () => {
    expect(source).toMatch(/\bp-4\b/);
    expect(source).toMatch(/\bsm:p-7\b/);
  });
});

describe("wide tables have a phone-sized alternative", () => {
  const screens: Array<[string, string]> = [
    ["routes/_app.students.index.tsx", "Student roster"],
    ["routes/_app.staff.index.tsx", "Staff roster"],
    ["routes/_app.platform.index.tsx", "schools needing attention"],
  ];

  it.each(screens)("%s pairs its table with a card list", (file) => {
    const source = read(file);
    // The table is hidden below `md`, and a card list is shown in its place.
    expect(source).toMatch(/hidden[^\n]*md:block|md:table/);
    expect(source).toContain("md:hidden");
  });

  it("the student table is the widest and is not rendered on a phone", () => {
    const source = read("routes/_app.students.index.tsx");
    expect(source).toContain("min-w-[52rem]");
    // The wide table must be inside the `md:` (tablet and up) branch.
    const tableAt = source.indexOf("min-w-[52rem]");
    const hiddenAt = source.lastIndexOf("hidden", tableAt);
    expect(hiddenAt).toBeGreaterThan(-1);
  });
});

describe("no fixed multi-column grid below the smallest breakpoint", () => {
  it("the promotion stat strip steps up rather than staying at 4 columns", () => {
    const source = read("routes/_app.promotion.tsx");
    // Whitespace-delimited so the token check cannot be fooled by
    // `sm:grid-cols-4`, which contains "grid-cols-4" as a substring.
    // The invariant is "one or two columns on a phone, more once there is
    // room", so the upper bound is not pinned to a column count: adding a KPI
    // must not require editing this test.
    expect(source).not.toMatch(/(?:^|\s)grid-cols-[3-9](?:\s|$)/);
    expect(source).toMatch(/grid-cols-2[^\n]*sm:grid-cols-\d/);
  });
});
