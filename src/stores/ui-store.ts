import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AppUiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

/**
 * Lightweight client-only UI state persisted to localStorage.
 * Drives the desktop sidebar collapsed/expanded state (spec §46).
 */
export const useAppUiStore = create<AppUiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: "fn.ui.v1" },
  ),
);
