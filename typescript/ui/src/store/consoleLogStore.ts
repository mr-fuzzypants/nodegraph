import { create } from 'zustand';

export type ConsoleLogSource = 'stdout' | 'stderr' | 'system';

export interface ConsoleLogEntry {
  id: string;
  source: ConsoleLogSource;
  message: string;
  nodeId?: string;
  nodeName?: string;
  timestamp: number;
}

interface ConsoleLogStore {
  entries: ConsoleLogEntry[];
  addEntry: (entry: Omit<ConsoleLogEntry, 'id' | 'timestamp'> & { timestamp?: number }) => void;
  clear: () => void;
}

const MAX_ENTRIES = 1000;

export const useConsoleLogStore = create<ConsoleLogStore>((set) => ({
  entries: [],

  addEntry: (entry) =>
    set((state) => ({
      entries: [
        ...state.entries,
        {
          ...entry,
          id: crypto.randomUUID(),
          timestamp: entry.timestamp ?? Date.now(),
        },
      ].slice(-MAX_ENTRIES),
    })),

  clear: () => set({ entries: [] }),
}));
