import { create } from 'zustand';
import { graphClient } from '../api/graphClient';
import type { NetworkListItem } from '../types/uiTypes';

// ─────────────────────────────────────────────────────────────────────────────
// Global store — shared, pane-independent metadata.
// Per-pane state (current network, breadcrumb, nodes, edges) lives in paneStore.
// ─────────────────────────────────────────────────────────────────────────────

interface GraphStore {
  // Shared across all panes
  nodeTypes: string[];
  allNetworks: NetworkListItem[];
  rootNetworkId: string | null;
  rootNetworkName: string;

  // Global UI state
  loading: boolean;
  error: string | null;

  // Actions
  init: () => Promise<void>;
  setError: (msg: string | null) => void;
}

export const useGraphStore = create<GraphStore>((set) => ({
  nodeTypes: [],
  allNetworks: [],
  rootNetworkId: null,
  rootNetworkName: 'root',
  loading: false,
  error: null,

  setError: (msg) => set({ error: msg }),

  init: async () => {
    set({ loading: true, error: null });
    try {
      const [rootInfo, nodeTypes, allNetworks] = await Promise.all([
        graphClient.getRootNetwork(),
        graphClient.getNodeTypes(),
        graphClient.listNetworks(),
      ]);
      set({
        nodeTypes,
        allNetworks,
        rootNetworkId: rootInfo.id,
        rootNetworkName: rootInfo.name ?? 'root',
      });
    } catch (e: any) {
      set({ error: e.message });
    } finally {
      set({ loading: false });
    }
  },
}));

