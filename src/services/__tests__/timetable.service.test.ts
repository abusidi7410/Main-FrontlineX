import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/api/client";
import {
  createTimetableEntry,
  createTimetablePeriod,
  deleteTimetableEntry,
  deleteTimetablePeriod,
  getTimetable,
  getTimetableGrid,
  updateTimetableEntry,
  updateTimetablePeriod,
} from "@/services/school.service";
import type { TimetableEntry, TimetableGrid } from "@/types";

/**
 * The timetable endpoint returns one grid (periods + lessons + the reference
 * lists the editor offers) rather than a bare list, so these tests pin the two
 * things that could quietly break a screen: the shape the grid consumers read,
 * and the endpoints each write goes to.
 */
vi.mock("@/api/client", () => ({ apiFetch: vi.fn() }));

const entry: TimetableEntry = {
  id: "12",
  day: 0,
  weekday: 0,
  dayName: "Monday",
  dayShort: "Mon",
  period: "P1",
  periodId: "3",
  classId: "7",
  className: "JSS 1",
  subject: "Mathematics",
  teacher: "Amoah Grace",
  teacherId: "5",
  room: "Room 1",
};

const grid: TimetableGrid = {
  session: "2026/2027",
  term: "First Term",
  days: [0, 1, 2, 3, 4],
  dayNames: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
  dayShortNames: ["Mon", "Tue", "Wed", "Thu", "Fri"],
  periods: [
    {
      id: "3",
      name: "P1",
      startTime: "08:00",
      endTime: "08:40",
      sortOrder: 1,
      isBreak: false,
    },
  ],
  entries: [entry],
  scope: { classId: "7", teacherId: "" },
  classes: [{ id: "7", name: "JSS 1", level: "JSS" }],
  classIds: { "JSS 1": "7" },
  subjects: ["Mathematics"],
  teachers: [{ id: "5", name: "Amoah Grace" }],
  rooms: ["Room 1"],
};

describe("getTimetableGrid", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("asks for the whole school when no scope is given", async () => {
    vi.mocked(apiFetch).mockResolvedValue(grid);
    await getTimetableGrid();
    expect(apiFetch).toHaveBeenCalledWith("/timetable", { query: {} });
  });

  it("narrows the request to one class", async () => {
    vi.mocked(apiFetch).mockResolvedValue(grid);
    await getTimetableGrid({ classId: "7" });
    expect(apiFetch).toHaveBeenCalledWith("/timetable", { query: { classId: "7" } });
  });

  it("narrows the request to one teacher", async () => {
    vi.mocked(apiFetch).mockResolvedValue(grid);
    await getTimetableGrid({ teacherId: "5" });
    expect(apiFetch).toHaveBeenCalledWith("/timetable", { query: { teacherId: "5" } });
  });

  it("passes the reference lists through for the editor", async () => {
    vi.mocked(apiFetch).mockResolvedValue(grid);
    const result = await getTimetableGrid({ classId: "7" });
    expect(result.periods[0]?.name).toBe("P1");
    expect(result.classes[0]?.name).toBe("JSS 1");
    expect(result.teachers[0]?.name).toBe("Amoah Grace");
    expect(result.rooms).toContain("Room 1");
    expect(result.days).toEqual([0, 1, 2, 3, 4]);
  });
});

describe("getTimetable", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("unwraps the grid into the flat lesson list list screens read", async () => {
    // "My classes" reads className off each row, so the flat shape has to
    // survive the move to the richer grid payload.
    vi.mocked(apiFetch).mockResolvedValue(grid);
    const result = await getTimetable();
    expect(result).toHaveLength(1);
    expect(result[0]?.className).toBe("JSS 1");
    expect(result[0]?.dayName).toBe("Monday");
  });

  it("returns an empty list rather than throwing on an unscheduled school", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...grid, entries: [] });
    await expect(getTimetable()).resolves.toEqual([]);
  });
});

describe("timetable lesson writes", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("posts a new lesson with its day, period and class", async () => {
    vi.mocked(apiFetch).mockResolvedValue(entry);
    await createTimetableEntry({
      weekday: 0,
      periodId: "3",
      classId: "7",
      subject: "Mathematics",
      teacherId: "5",
      room: "Room 1",
    });
    expect(apiFetch).toHaveBeenCalledWith("/timetable/entries", {
      method: "POST",
      body: {
        weekday: 0,
        periodId: "3",
        classId: "7",
        subject: "Mathematics",
        teacherId: "5",
        room: "Room 1",
      },
    });
  });

  it("sends an empty teacher to unassign rather than omitting the field", async () => {
    // Omitting it would leave the existing teacher in place, which is the
    // opposite of what clearing the dropdown means.
    vi.mocked(apiFetch).mockResolvedValue(entry);
    await createTimetableEntry({
      weekday: 0,
      periodId: "3",
      classId: "7",
      subject: "Mathematics",
      teacherId: "",
    });
    const [, options] = vi.mocked(apiFetch).mock.calls[0]!;
    expect((options?.body as { teacherId: string }).teacherId).toBe("");
  });

  it("patches only the fields that changed", async () => {
    vi.mocked(apiFetch).mockResolvedValue(entry);
    await updateTimetableEntry("12", { subject: "Basic Science" });
    expect(apiFetch).toHaveBeenCalledWith("/timetable/entries/12", {
      method: "PATCH",
      body: { subject: "Basic Science" },
    });
  });

  it("deletes the lesson by id", async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined);
    await deleteTimetableEntry("12");
    expect(apiFetch).toHaveBeenCalledWith("/timetable/entries/12", { method: "DELETE" });
  });
});

describe("timetable period writes", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("posts a period with 24-hour times", async () => {
    const period = {
      id: "11",
      name: "Chapel",
      startTime: "10:00",
      endTime: "10:25",
      sortOrder: 9,
      isBreak: true,
    };
    vi.mocked(apiFetch).mockResolvedValue(period);
    const result = await createTimetablePeriod({
      name: "Chapel",
      startTime: "10:00",
      endTime: "10:25",
      isBreak: true,
    });
    expect(apiFetch).toHaveBeenCalledWith("/timetable/periods", {
      method: "POST",
      body: { name: "Chapel", startTime: "10:00", endTime: "10:25", isBreak: true },
    });
    expect(result.isBreak).toBe(true);
  });

  it("patches a period", async () => {
    vi.mocked(apiFetch).mockResolvedValue(grid.periods[0]);
    await updateTimetablePeriod("3", { startTime: "08:10" });
    expect(apiFetch).toHaveBeenCalledWith("/timetable/periods/3", {
      method: "PATCH",
      body: { startTime: "08:10" },
    });
  });

  it("deletes a period by id", async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined);
    await deleteTimetablePeriod("3");
    expect(apiFetch).toHaveBeenCalledWith("/timetable/periods/3", { method: "DELETE" });
  });
});
