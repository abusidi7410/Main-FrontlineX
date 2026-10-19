import { describe, expect, it } from "vitest";
import {
  EMPTY_ADMISSION,
  toAdmissionInput,
  toFormValues,
  type AdmissionFormValues,
} from "../admission-wizard";
import type { AdmissionApplication } from "@/types";

function makeApplication(overrides: Partial<AdmissionApplication> = {}): AdmissionApplication {
  return {
    id: "app_1",
    status: "draft",
    applicantType: "new",
    firstName: "Ada",
    middleName: "Nneka",
    lastName: "Okafor",
    gender: "female",
    dateOfBirth: "2018-04-12",
    nationality: "Nigerian",
    stateOfOrigin: "Anambra",
    lgaOfOrigin: "Awka South",
    religion: "Christianity",
    classId: 7,
    className: "Primary 2",
    levelCode: "PRY",
    academicSessionId: 3,
    academicSession: "2025/2026",
    admissionYear: 2026,
    guardianName: "Chidi Okafor",
    guardianRelationship: "Father",
    guardianPhone: "+2348012345678",
    guardianEmail: "chidi@example.com",
    guardianOccupation: "Engineer",
    guardianAddress: "12 Awka Road",
    secondGuardianName: "",
    secondGuardianPhone: "",
    bloodGroup: "O+",
    allergies: "",
    medicalConditions: "",
    emergencyContactName: "Ngozi Okafor",
    emergencyContactPhone: "08098765432",
    previousSchoolName: "",
    previousSchoolAddress: "",
    lastClassCompleted: "",
    reasonForTransfer: "",
    refereeName: "",
    refereePhone: "",
    refereeAddress: "",
    sponsorName: "",
    sponsorRelationship: "",
    sponsorPhone: "",
    sponsorEmail: "",
    sponsorAddress: "",
    mailingAddress: "",
    declaredBy: "Chidi Okafor",
    declaredAt: "2026-01-04T09:00:00Z",
    submittedAt: null,
    reviewedBy: "",
    reviewedAt: null,
    decisionReason: "",
    admissionNumber: "",
    studentId: null,
    duplicateOf: null,
    requiredDocuments: [],
    missingDocuments: [],
    createdBy: "Bursar",
    createdAt: "2026-01-04T08:55:00Z",
    lastSavedAt: "2026-01-04T09:00:00Z",
    ...overrides,
  };
}

function formValues(overrides: Partial<AdmissionFormValues> = {}): AdmissionFormValues {
  return { ...EMPTY_ADMISSION, ...overrides };
}

describe("toAdmissionInput", () => {
  it("addresses the class by id and attaches the current session", () => {
    const input = toAdmissionInput(
      formValues({ className: "Primary 2", firstName: "Ada" }),
      { "Primary 2": 7 },
      3,
    );

    expect(input.classId).toBe(7);
    expect(input.academicSessionId).toBe(3);
    expect(input.firstName).toBe("Ada");
  });

  it("normalises a Nigerian phone number before sending it", () => {
    const input = toAdmissionInput(formValues({ guardianPhone: "0801 234 5678" }), {}, null);

    expect(input.guardianPhone).toBe("+2348012345678");
  });

  it("drops an unknown class and an impossible admission year", () => {
    const input = toAdmissionInput(
      formValues({ className: "JSS 9", admissionYear: "1800" }),
      { "Primary 2": 7 },
      null,
    );

    expect(input.classId).toBeNull();
    expect(input.admissionYear).toBeNull();
  });

  it("keeps a valid admission year as a number", () => {
    const input = toAdmissionInput(formValues({ admissionYear: "2026" }), {}, null);

    expect(input.admissionYear).toBe(2026);
  });
});

describe("toFormValues", () => {
  it("round-trips the fields the wizard edits", () => {
    const values = toFormValues(makeApplication());

    expect(values.firstName).toBe("Ada");
    expect(values.middleName).toBe("Nneka");
    expect(values.className).toBe("Primary 2");
    expect(values.gender).toBe("female");
    expect(values.guardianPhone).toBe("+2348012345678");
    expect(values.admissionYear).toBe("2026");
    expect(values.declaredBy).toBe("Chidi Okafor");
  });

  it("falls back to safe values for an incomplete draft", () => {
    const values = toFormValues(
      makeApplication({ gender: "", dateOfBirth: null, admissionYear: null, className: "" }),
    );

    expect(values.gender).toBe("male");
    expect(values.dateOfBirth).toBe("");
    expect(values.admissionYear).toBe("");
    expect(values.className).toBe("");
  });
});
