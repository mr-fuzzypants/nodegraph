/**
 * paneStore — creates an independent Zustand store for one graph pane.
 *
 * Each split pane gets its own store instance so it can navigate the graph
 * tree independently (different current network, breadcrumb, etc.).
 */
import { createStore } from 'zustand';
import type { Connection, Edge as FlowEdge, Node as FlowNode } from '@xyflow/react';
import { graphClient } from '../api/graphClient';
import type { NodeData, SerializedNetwork } from '../types/uiTypes';

// ── Types ──────────────────────────────────────────────────────────────────────

interface BreadcrumbEntry {
  id: string;
  name: string;
}

export interface PaneState {
  currentNetworkId: string | null;
  breadcrumb: BreadcrumbEntry[];
  nodes: FlowNode<NodeData>[];
  edges: FlowEdge[];
  paneLoading: boolean;

  // ── Navigation ──
  loadNetwork: (networkId: string, name?: string) => Promise<void>;
  enterSubnetwork: (subnetworkId: string, name: string) => Promise<void>;
  exitTo: (breadcrumbIndex: number) => Promise<void>;
  /** Silently re-fetch the current network and update node/port values in place. */
  refreshNodes: () => Promise<void>;

  // ── Graph mutations ──
  createNode: (type: string, position: { x: number; y: number }) => Promise<void>;
  createSubnetwork: (name: string, position: { x: number; y: number }) => Promise<void>;
  deleteNode: (nodeId: string) => Promise<void>;
  onConnect: (connection: Connection) => Promise<void>;
  onNodesChange: (nodeId: string, x: number, y: number) => Promise<void>;
  executeNode: (nodeId: string) => Promise<void>;

  /** Directly set an input port's value (for unconnected ports). */
  setPortValue: (nodeId: string, portName: string, value: any) => Promise<void>;

  // ── Tunnel port management ──
  addTunnelPort: (name: string, direction: 'input' | 'output') => Promise<void>;
  removeTunnelPort: (name: string, direction: 'input' | 'output') => Promise<void>;
}

export type PaneStore = ReturnType<typeof createPaneStore>;

// ── Helper ─────────────────────────────────────────────────────────────────────

export function networkToFlow(
  network: SerializedNetwork,
  onEnter: (sid: string, name: string) => void,
  onAddTunnelPort?: (name: string, direction: 'input' | 'output') => Promise<void>,
  onRemoveTunnelPort?: (name: string, direction: 'input' | 'output') => Promise<void>,
): { nodes: FlowNode<NodeData>[]; edges: FlowEdge[] } {
  const nodes: FlowNode<NodeData>[] = network.nodes.map((n) => ({
    id: n.id,
    type: n.kind === 'NETWORK' ? 'networkNode' : n.kind === 'SELF' ? 'tunnelNode' : 'functionNode',
    position: n.position,
    data: {
      label: n.name,
      nodeType: n.type,
      inputs: n.inputs,
      outputs: n.outputs,
      isFlowControlNode: n.isFlowControlNode,
      subnetworkId: n.subnetworkId,
      onEnter: n.subnetworkId ? (sid: string) => onEnter(sid, n.name) : undefined,
      // Tunnel port callbacks — only meaningful for SELF nodes, but harmless on others
      onAddTunnelPort,
      onRemoveTunnelPort,
    },
  }));

  const edges: FlowEdge[] = network.edges.map((e) => ({
    id: e.id,
    source: e.sourceNodeId,
    sourceHandle: `out-${e.sourcePortName}`,
    target: e.targetNodeId,
    targetHandle: `in-${e.targetPortName}`,
  }));

  return { nodes, edges };
}

// ── Factory ────────────────────────────────────────────────────────────────────

export function createPaneStore() {
  return createStore<PaneState>((set, get) => ({
    currentNetworkId: null,
    breadcrumb: [],
    nodes: [],
    edges: [],
    paneLoading: false,

    loadNetwork: async (networkId, name) => {
      set({ paneLoading: true });
      try {
        const network = await graphClient.getNetwork(networkId);
        const { nodes, edges } = networkToFlow(
          network,
          (sid, sname) => get().enterSubnetwork(sid, sname),
          (n, dir) => get().addTunnelPort(n, dir),
          (n, dir) => get().removeTunnelPort(n, dir),
        );
        set({
          currentNetworkId: networkId,
          nodes,
          edges,
          breadcrumb: [{ id: networkId, name: name ?? network.name }],
        });
      } finally {
        set({ paneLoading: false });
      }
    },

    refreshNodes: async () => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      try {
        const network = await graphClient.getNetwork(currentNetworkId);
        const { nodes: freshNodes, edges } = networkToFlow(
          network,
          (sid, sname) => get().enterSubnetwork(sid, sname),
          (n, dir) => get().addTunnelPort(n, dir),
          (n, dir) => get().removeTunnelPort(n, dir),
        );
        // Preserve ReactFlow selection state from the current nodes
        set((s) => ({
          edges,
          nodes: freshNodes.map((n) => ({
            ...n,
            selected: s.nodes.find((cur) => cur.id === n.id)?.selected ?? false,
          })),
        }));
      } catch {
        // Swallow — this is a background refresh; don't surface errors to the user
      }
    },

    enterSubnetwork: async (subnetworkId, name) => {
      set({ paneLoading: true });
      try {
        const network = await graphClient.getNetwork(subnetworkId);
        const { nodes, edges } = networkToFlow(
          network,
          (sid, sname) => get().enterSubnetwork(sid, sname),
          (n, dir) => get().addTunnelPort(n, dir),
          (n, dir) => get().removeTunnelPort(n, dir),
        );
        set((s) => ({
          currentNetworkId: subnetworkId,
          nodes,
          edges,
          breadcrumb: [...s.breadcrumb, { id: subnetworkId, name }],
        }));
      } finally {
        set({ paneLoading: false });
      }
    },

    exitTo: async (breadcrumbIndex) => {
      const { breadcrumb } = get();
      const target = breadcrumb[breadcrumbIndex];
      if (!target) return;
      set({ paneLoading: true });
      try {
        const network = await graphClient.getNetwork(target.id);
        const { nodes, edges } = networkToFlow(
          network,
          (sid, sname) => get().enterSubnetwork(sid, sname),
          (n, dir) => get().addTunnelPort(n, dir),
          (n, dir) => get().removeTunnelPort(n, dir),
        );
        set({
          currentNetworkId: target.id,
          nodes,
          edges,
          breadcrumb: breadcrumb.slice(0, breadcrumbIndex + 1),
        });
      } finally {
        set({ paneLoading: false });
      }
    },

    createNode: async (type, position) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const name = `${type}_${Date.now()}`;
      await graphClient.createNode(currentNetworkId, type, name, position);
      const network = await graphClient.getNetwork(currentNetworkId);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
      );
      set({ nodes, edges });
    },

    createSubnetwork: async (name, position) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.createSubnetwork(currentNetworkId, name);
      const network = await graphClient.getNetwork(currentNetworkId);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
      );
      set({ nodes, edges });
    },

    deleteNode: async (nodeId) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.deleteNode(currentNetworkId, nodeId);
      set((s) => ({
        nodes: s.nodes.filter((n) => n.id !== nodeId),
        edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      }));
    },

    onConnect: async (connection) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId || !connection.source || !connection.target) return;
      const sourcePort = connection.sourceHandle?.replace('out-', '') ?? '';
      const targetPort = connection.targetHandle?.replace('in-', '') ?? '';
      const network = await graphClient.addEdge(
        currentNetworkId,
        connection.source,
        sourcePort,
        connection.target,
        targetPort,
      );
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
      );
      set({ nodes, edges });
    },

    onNodesChange: async (nodeId, x, y) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      graphClient.setPosition(currentNetworkId, nodeId, x, y).catch(() => {});
    },

    executeNode: async (nodeId) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      // Import lazily to avoid module-level circular reference
      const { useTraceStore } = await import('./traceStore');
      useTraceStore.getState().clearTrace();
      const step = useTraceStore.getState().stepModeEnabled;
      await graphClient.execute(currentNetworkId, nodeId, step);
    },

    setPortValue: async (nodeId, portName, value) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.setPortValue(currentNetworkId, nodeId, portName, value);
      await get().refreshNodes();
    },

    addTunnelPort: async (name, direction) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const network = await graphClient.addTunnelPort(currentNetworkId, name, direction);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
      );
      set({ nodes, edges });
    },

    removeTunnelPort: async (name, direction) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.removeTunnelPort(currentNetworkId, name, direction);
      const network = await graphClient.getNetwork(currentNetworkId);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
      );
      set({ nodes, edges });
    },
  }));
}
