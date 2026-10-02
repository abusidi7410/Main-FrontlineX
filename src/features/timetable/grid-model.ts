import type { TimetableEntry, TimetablePeriod, TimetableWeekday } from "@/types";

/**
 * Pure grid logic, kept out of the component so it can be tested without a DOM
 * and so the same rules back every timetable view.
 *
 * A "slot" is one (weekday, period) cell for one class. Keying on the class as
 * well as the day and period is what lets the same grid render a single class's
 * week and a whole-school overview: in the overview a cell holds one lesson per
 * class, in the class view it holds at most one.
 */
export function slotKey(weekday: number, periodId: string, classId: string): string {
  return `${weekday}:${periodId}:${classId}`;
}

/** A grid cell: one (weekday, period) column pair, whichever classes are in it. */
export function cellKey(weekday: number, periodId: string): string {
  return `${weekday}:${periodId}`;
}

/**
 * Group lessons by the cell they render in.
 *
 * Unlike `indexEntriesBySlot` this ignores the class, because a grid cell shows
 * whatever falls in it: in a class-scoped view that is at most one lesson, and
 * in a whole-school overview it is one per class.
 */
export function indexEntriesByCell(entries: TimetableEntry[]): Map<string, TimetableEntry[]> {
  const byCell = new Map<string, TimetableEntry[]>();
  for (const entry of entries) {
    const key = cellKey(entry.weekday, entry.periodId);
    const bucket = byCell.get(key);
    if (bucket) {
      bucket.push(entry);
    } else {
      byCell.set(key, [entry]);
    }
  }
  return byCell;
}

/** Periods that can hold a lesson, in the order they occur in the day. */
export function lessonPeriods(periods: TimetablePeriod[]): TimetablePeriod[] {
  return periods.filter((period) => !period.isBreak);
}

/** Divider rows: they appear in the grid but never hold a lesson. */
export function breakPeriods(periods: TimetablePeriod[]): TimetablePeriod[] {
  return periods.filter((period) => period.isBreak);
}

/** Group lessons by the cell they occupy. */
export function indexEntriesBySlot(entries: TimetableEntry[]): Map<string, TimetableEntry[]> {
  const bySlot = new Map<string, TimetableEntry[]>();
  for (const entry of entries) {
    const key = slotKey(entry.weekday, entry.periodId, entry.classId);
    const bucket = bySlot.get(key);
    if (bucket) {
      bucket.push(entry);
    } else {
      bySlot.set(key, [entry]);
    }
  }
  return bySlot;
}

/** The lessons in one cell, or an empty array when the slot is free. */
export function entriesAt(
  bySlot: Map<string, TimetableEntry[]>,
  weekday: TimetableWeekday,
  periodId: string,
  classId: string,
): TimetableEntry[] {
  return bySlot.get(slotKey(weekday, periodId, classId)) ?? [];
}

/** The lesson in a class's slot, if it is taken. */
export function entryAt(
  entries: TimetableEntry[],
  weekday: number,
  periodId: string,
  classId: string,
): TimetableEntry | undefined {
  return entries.find(
    (entry) =>
      entry.weekday === weekday && entry.periodId === periodId && entry.classId === classId,
  );
}

/** How full the school day is, used for the summary line under the grid. */
export function timetableSummary(
  periods: TimetablePeriod[],
  entries: TimetableEntry[],
): { scheduled: number; capacity: number; unassignedTeacher: number; unassignedRoom: number } {
  const slots = lessonPeriods(periods).length;
  // One cell per (class, teaching day, lesson period).
  const capacity = slots * new Set(entries.map((entry) => entry.classId)).size;
  return {
    scheduled: entries.length,
    capacity,
    unassignedTeacher: entries.filter((entry) => !entry.teacher).length,
    unassignedRoom: entries.filter((entry) => !entry.room).length,
  };
}
