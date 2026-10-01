import type { AttendanceSubmission } from "@/types";

/**
 * IndexedDB queue for teacher devices. Everything a teacher does offline lands
 * here first, then the sync centre drains it when connectivity returns.
 */
const DB_NAME = "frontline-nexus";
const DB_VERSION = 1;
const STORE = "attendance_queue";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open local storage"));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest,
): Promise<T> {
  const db = await openDb();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = fn(tx.objectStore(STORE));
    let result: T;
    let requestSucceeded = false;
    let settled = false;
    const fail = (error: DOMException | null) => {
      if (settled) return;
      settled = true;
      db.close();
      reject(error ?? new Error("Local storage transaction failed"));
    };
    request.onsuccess = () => {
      result = request.result as T;
      requestSucceeded = true;
    };
    request.onerror = () => fail(request.error);
    tx.oncomplete = () => {
      if (settled) return;
      if (!requestSucceeded) {
        fail(tx.error);
        return;
      }
      settled = true;
      db.close();
      resolve(result);
    };
    tx.onerror = () => fail(tx.error);
    tx.onabort = () => fail(tx.error);
  });
}

export async function queueAttendance(submission: AttendanceSubmission) {
  await withStore("readwrite", (store) => store.put(submission));
}

export async function listQueuedAttendance(): Promise<AttendanceSubmission[]> {
  const all = await withStore<AttendanceSubmission[]>("readonly", (store) => store.getAll());
  return all.sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function removeQueuedAttendance(id: string) {
  await withStore("readwrite", (store) => store.delete(id));
}

export async function markQueuedState(id: string, syncState: AttendanceSubmission["syncState"]) {
  const existing = await withStore<AttendanceSubmission | undefined>("readonly", (store) =>
    store.get(id),
  );
  if (!existing) return;
  await queueAttendance({ ...existing, syncState, updatedAt: Date.now() });
}
