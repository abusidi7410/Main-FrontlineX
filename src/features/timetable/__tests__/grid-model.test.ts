import { describe, expect, it } from "vitest";

import {
  breakPeriods,
  cellKey,
  entriesAt,
  entryAt,
  indexEntriesByCell,
  indexEntriesBySlot,
  lessonPeriods,
  timetableSummary,
} from "@/features/timetable/grid-model";
import type { TimetableEntry, TimetablePeriod } from "@/types";

/**
 * The grid's cell placement is the one piece of the timetable screen that can
 * go quietly wrong: a lesson rendered in the wrong cell, or a break row that
 * accepts one. Both are invisible in a screenshot and obvious to a teacher.
 */
function period(id: string, name: string, sortOrder: number, isBreak = false): TimetablePeriod {
  return {
    id,
    name,
    startTime: `0${8 + Math.floor(sortOrder / 2)}:${sortOrder % 2 === 0 ? "00" : "40"}`,
    endTime: `0${8 + Math.floor(sortOrder / 2)}:${sortOrder % 2 === 0 ? "40" : "59"}`,
    sortOrder,
    isBreak,
  };
}

function lesson(overrides: Partial<TimetableEntry> = {}): TimetableEntry {
  return {
    id: "1",
    day: 0,
    weekday: 0,
    dayName: "Monday",
    dayShort: "Mon",
    period: "P1",
    periodId: "p1",
    classId: "jss1",
    className: "JSS 1",
    subject: "Mathematics",
    teacher: "Amoah Grace",
    teacherId: "t1",
    room: "Room 1",
    ...overrides,
  };
}

const day = [period("p1", "P1", 1), period("brk", "Break", 2, true), period("p2", "P2", 3)];

describe("period rows", () => {
  it("separates lesson periods from breaks, keeping their order", () => {
    expect(lessonPeriods(day).map((row) => row.name)).toEqual(["P1", "P2"]);
    expect(breakPeriods(day).map((row) => row.name)).toEqual(["Break"]);
  });

  it("puts the break between P1 and P2 rather than at the end", () => {
    // The seeded day interleaves breaks, so the grid has to render them in
    // sequence, not append them.
    const rows = [...lessonPeriods(day), ...breakPeriods(day)];
    expect(rows.map((row) => row.name)).toContain("Break");
    expect(lessonPeriods(day)[0]?.name).toBe("P1");
  });
});

describe("indexEntriesByCell", () => {
  it("puts each lesson in the cell for its day and period", () => {
    const byCell = indexEntriesByCell([
      lesson({ id: "a" }),
      lesson({ id: "b", weekday: 1, dayName: "Tuesday", dayShort: "Tue", periodId: "p1" }),
      lesson({ id: "c", periodId: "p2", period: "P2" }),
    ]);
    expect(byCell.get(cellKey(0, "p1"))?.map((row) => row.id)).toEqual(["a"]);
    expect(byCell.get(cellKey(1, "p1"))?.map((row) => row.id)).toEqual(["b"]);
    expect(byCell.get(cellKey(0, "p2"))?.map((row) => row.id)).toEqual(["c"]);
  });

  it("collects every class's lesson in one cell for a school-wide view", () => {
    const byCell = indexEntriesByCell([
      lesson({ id: "a", classId: "jss1", className: "JSS 1" }),
      lesson({ id: "b", classId: "jss2", className: "JSS 2" }),
      lesson({ id: "c", classId: "sss1", className: "SSS 1" }),
    ]);
    expect(byCell.get(cellKey(0, "p1"))).toHaveLength(3);
  });

  it("leaves an unscheduled cell empty rather than inventing a row", () => {
    const byCell = indexEntriesByCell([lesson()]);
    expect(byCell.get(cellKey(3, "p1"))).toBeUndefined();
  });

  it("handles an empty timetable", () => {
    expect(indexEntriesByCell([]).size).toBe(0);
  });
});

describe("indexEntriesBySlot", () => {
  it("separates the same cell across classes", () => {
    const bySlot = indexEntriesBySlot([
      lesson({ id: "a", classId: "jss1" }),
      lesson({ id: "b", classId: "jss2" }),
    ]);
    expect(bySlot.get("0:p1:jss1")?.map((row) => row.id)).toEqual(["a"]);
    expect(bySlot.get("0:p1:jss2")?.map((row) => row.id)).toEqual(["b"]);
  });
});

describe("entriesAt and entryAt", () => {
  const entries = [lesson({ id: "a" }), lesson({ id: "b", classId: "jss2" })];

  it("returns the lessons for a class's slot", () => {
    const bySlot = indexEntriesBySlot(entries);
    expect(entriesAt(bySlot, 0, "p1", "jss1").map((row) => row.id)).toEqual(["a"]);
  });

  it("returns an empty array for a free slot", () => {
    const bySlot = indexEntriesBySlot(entries);
    expect(entriesAt(bySlot, 2, "p2", "jss1")).toEqual([]);
  });

  it("finds the single lesson in a class's slot for the editor", () => {
    expect(entryAt(entries, 0, "p1", "jss1")?.id).toBe("a");
    expect(entryAt(entries, 0, "p1", "sss1")).toBeUndefined();
  });
});

describe("timetableSummary", () => {
  it("counts lessons against the lesson periods, not the breaks", () => {
    const summary = timetableSummary(day, [
      lesson({ id: "a" }),
      lesson({ id: "b", classId: "jss2" }),
    ]);
    // Two lesson periods x two classes on the timetable = four possible slots.
    expect(summary.scheduled).toBe(2);
    expect(summary.capacity).toBe(4);
  });

  it("flags lessons still missing a teacher or a room", () => {
    const summary = timetableSummary(day, [
      lesson({ id: "a", teacher: "", teacherId: "" }),
      lesson({ id: "b", classId: "jss2", room: "" }),
      lesson({ id: "c", classId: "sss1" }),
    ]);
    expect(summary.unassignedTeacher).toBe(1);
    expect(summary.unassignedRoom).toBe(1);
  });

  it("reports zero capacity for a school with no lessons", () => {
    expect(timetableSummary(day, [])).toMatchObject({ scheduled: 0, capacity: 0 });
  });
});
