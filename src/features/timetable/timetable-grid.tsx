import { CalendarClock, MapPin, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  breakPeriods,
  cellKey,
  indexEntriesByCell,
  lessonPeriods,
} from "@/features/timetable/grid-model";
import type { TimetableEntry, TimetablePeriod, TimetableWeekday } from "@/types";
import { TIMETABLE_WEEKDAY_SHORT } from "@/types";

/**
 * The week grid: one row per bell, one column per teaching day.
 *
 * Rendered as a real `<table>` because it is tabular data that a screen reader
 * needs to be able to navigate cell by cell, and because the period times are
 * row headers. A CSS grid of divs would read as one long unstructured list.
 *
 * Break rows span the week: a break is a divider in the day, not a lesson, so
 * it has no cells to fill.
 */
export function TimetableGrid({
  days,
  periods,
  entries,
  editable = false,
  onSelectSlot,
}: {
  days: TimetableWeekday[];
  periods: TimetablePeriod[];
  entries: TimetableEntry[];
  /** Only class-scoped views can be edited; an overview of many classes cannot. */
  editable?: boolean;
  onSelectSlot?: (weekday: number, periodId: string) => void;
}) {
  const rows = lessonPeriods(periods);
  const breaks = breakPeriods(periods);
  const byCell = indexEntriesByCell(entries);

  return (
    <div className="fn-panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Weekly timetable. Each row is a period and each column is a teaching day.
          </caption>
          <thead>
            <tr className="border-b bg-muted/40">
              <th scope="col" className="w-32 px-4 py-3 text-left align-bottom font-medium">
                Period
              </th>
              {days.map((day) => (
                <th key={day} scope="col" className="px-4 py-3 text-left align-bottom font-medium">
                  {TIMETABLE_WEEKDAY_SHORT[day]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((period) => (
              <tr key={period.id} className="border-b last:border-b-0 align-top">
                <th scope="row" className="px-4 py-3 text-left font-normal">
                  <span className="block font-medium">{period.name}</span>
                  <span className="block text-xs text-muted-foreground tabular-nums">
                    {period.startTime}–{period.endTime}
                  </span>
                </th>
                {days.map((day) => (
                  <td key={day} className="px-2 py-2">
                    <SlotCell
                      entries={byCell.get(cellKey(day, period.id)) ?? []}
                      editable={editable}
                      onSelect={() => onSelectSlot?.(day, period.id)}
                    />
                  </td>
                ))}
              </tr>
            ))}
            {breaks.map((period) => (
              <tr key={period.id} className="border-b bg-brass-soft/40 last:border-b-0">
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  <span className="block text-sm font-medium">{period.name}</span>
                  <span className="block text-xs text-muted-foreground tabular-nums">
                    {period.startTime}–{period.endTime}
                  </span>
                </th>
                <td colSpan={Math.max(days.length, 1)} className="px-4 py-2 text-center">
                  <span className="fn-eyebrow">Break — no lessons are timetabled</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SlotCell({
  entries,
  editable,
  onSelect,
}: {
  entries: TimetableEntry[];
  editable: boolean;
  onSelect: () => void;
}) {
  if (entries.length === 0) {
    if (!editable) {
      return (
        <div
          className="min-h-16 rounded-lg border border-dashed border-border"
          aria-hidden="true"
        />
      );
    }
    return (
      <button
        type="button"
        onClick={onSelect}
        className="flex min-h-16 w-full items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground transition-colors hover:border-brass hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
      >
        Add lesson
      </button>
    );
  }

  return (
    <ul className="space-y-1.5">
      {entries.map((entry) => (
        <li key={entry.id}>
          <LessonCard entry={entry} editable={editable} onSelect={onSelect} />
        </li>
      ))}
    </ul>
  );
}

function LessonCard({
  entry,
  editable,
  onSelect,
}: {
  entry: TimetableEntry;
  editable: boolean;
  onSelect: () => void;
}) {
  const body = (
    <>
      <p className="flex items-start gap-1.5 font-medium leading-snug">
        <CalendarClock className="mt-0.5 size-3.5 shrink-0 text-brass" aria-hidden="true" />
        <span className="min-w-0 break-words">{entry.subject}</span>
      </p>
      <p className="mt-1 space-y-0.5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <User className="size-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{entry.teacher || "No teacher assigned"}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <MapPin className="size-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{entry.room || "No room booked"}</span>
        </span>
      </p>
    </>
  );

  if (!editable) {
    return <div className="fn-panel-hover rounded-lg border bg-card p-2.5">{body}</div>;
  }

  return (
    <Button
      type="button"
      variant="ghost"
      onClick={onSelect}
      className="h-auto w-full justify-start whitespace-normal rounded-lg border bg-card p-2.5 text-left font-normal hover:bg-muted"
    >
      {body}
    </Button>
  );
}
