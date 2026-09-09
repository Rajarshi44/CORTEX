"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { EntityType, User } from "./types";

export type Lens = "overview" | "chart" | "players" | "alerts" | "map" | "investigator" | "sources" | "ledger";

interface SheetState {
  user: User | null;
  setUser: (u: User | null) => void;

  /** Presentation mode: larger type, thinner marginalia, slower pacing. Data and caveats never change. */
  presentation: boolean;
  setPresentation: (v: boolean) => void;

  /** The selected entity stays highlighted across every lens (wayfinding raise). */
  selected: string | null;
  select: (id: string | null) => void;
  /** Node ids the investigator or an alert asked us to emphasise; everything else recedes. */
  highlights: string[];
  setHighlights: (ids: string[], narrative?: string) => void;
  /** A path drawn as the red course line. */
  route: string[] | null;
  setRoute: (ids: string[] | null) => void;
  /** Narrative line for the last chart transition (alphabet-storm raise); read by the live region. */
  narrative: string;
  setNarrative: (s: string) => void;

  /** Symbol-key filters. Empty = all. */
  hiddenTypes: EntityType[];
  toggleType: (t: EntityType) => void;
  hiddenRelations: string[];
  toggleRelation: (r: string) => void;
  minPriority: number;
  setMinPriority: (v: number) => void;

  /** Scrubber: time window in ISO dates, or null for whole sheet (specimen raise). */
  timeWindow: [string, string] | null;
  setTimeWindow: (w: [string, string] | null) => void;

  commandOpen: boolean;
  setCommandOpen: (v: boolean) => void;
  notesOpen: boolean;
  setNotesOpen: (v: boolean) => void;
}

export const useSheet = create<SheetState>()(
  persist(
    (set, get) => ({
      user: null,
      setUser: (user) => set({ user }),
      presentation: false,
      setPresentation: (presentation) => set({ presentation }),
      selected: null,
      select: (selected) => set({ selected, notesOpen: selected !== null }),
      highlights: [],
      setHighlights: (highlights, narrative) => set({ highlights, ...(narrative !== undefined ? { narrative } : {}) }),
      route: null,
      setRoute: (route) => set({ route }),
      narrative: "",
      setNarrative: (narrative) => set({ narrative }),
      hiddenTypes: [],
      toggleType: (t) => set({ hiddenTypes: get().hiddenTypes.includes(t) ? get().hiddenTypes.filter((x) => x !== t) : [...get().hiddenTypes, t] }),
      hiddenRelations: [],
      toggleRelation: (r) => set({ hiddenRelations: get().hiddenRelations.includes(r) ? get().hiddenRelations.filter((x) => x !== r) : [...get().hiddenRelations, r] }),
      minPriority: 0,
      setMinPriority: (minPriority) => set({ minPriority }),
      timeWindow: null,
      setTimeWindow: (timeWindow) => set({ timeWindow }),
      commandOpen: false,
      setCommandOpen: (commandOpen) => set({ commandOpen }),
      notesOpen: false,
      setNotesOpen: (notesOpen) => set({ notesOpen }),
    }),
    {
      name: "cortex.sheet",
      partialize: (s) => ({ presentation: s.presentation, hiddenTypes: s.hiddenTypes, hiddenRelations: s.hiddenRelations, minPriority: s.minPriority, user: s.user }),
    },
  ),
);
