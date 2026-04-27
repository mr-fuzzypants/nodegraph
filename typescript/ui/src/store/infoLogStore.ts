import { create } from 'zustand';

export type InfoLogKind = 'api' | 'websocket' | 'system';
export type InfoLogStatus = 'pending' | 'success' | 'error' | 'info';

export interface InfoLogEntry {
  id: string;
  kind: InfoLogKind;
  status: InfoLogStatus;
  message: string;
  timestamp: number;
}

interface InfoLogStore {
  entries: InfoLogEntry[];
  addEntry: (entry: Omit<InfoLogEntry, 'id' | 'timestamp'> & { timestamp?: number }) => void;
  clear: () => void;
}

const MAX_ENTRIES = 500;

export const useInfoLogStore = create<InfoLogStore>((set) => ({
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
