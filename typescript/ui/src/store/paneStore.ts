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

function toGraphNodeId(nodeId: string): string {
  if (nodeId.endsWith(':in') || nodeId.endsWith(':out')) {
    return nodeId.slice(0, nodeId.lastIndexOf(':'));
  }
  return nodeId;
}

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
  groupNodes: (nodeIds: string[]) => Promise<void>;
  deleteNode: (nodeId: string) => Promise<void>;
  renameNode: (nodeId: string, name: string) => Promise<void>;
  deleteEdge: (edgeId: string) => Promise<void>;
  onConnect: (connection: Connection) => Promise<void>;
  onNodesChange: (nodeId: string, x: number, y: number) => Promise<void>;
  executeNode: (nodeId: string) => Promise<void>;
  setSelection: (nodeIds: string[], edgeIds: string[]) => void;
  saveSelection: (name: string) => Promise<void>;

  /** Directly set an input port's value (for unconnected ports). */
  setPortValue: (nodeId: string, portName: string, value: any) => Promise<void>;

  // ── Tunnel port management ──
  addTunnelPort: (
    name: string,
    direction: 'input' | 'output',
    portFunction?: 'DATA' | 'CONTROL',
    valueType?: string,
  ) => Promise<void>;
  connectToNewTunnelInput: (sourceNodeId: string, sourcePort: string) => Promise<void>;
  connectNewTunnelInputToTarget: (targetNodeId: string, targetPort: string) => Promise<void>;
  connectToNewTunnelOutput: (sourceNodeId: string, sourcePort: string) => Promise<void>;
  removeTunnelPort: (name: string, direction: 'input' | 'output') => Promise<void>;
  renameTunnelPort: (oldName: string, newName: string, direction: 'input' | 'output') => Promise<void>;
}

export type PaneStore = ReturnType<typeof createPaneStore>;

// ── Helper ─────────────────────────────────────────────────────────────────────

export function networkToFlow(
  network: SerializedNetwork,
  onEnter: (sid: string, name: string) => void,
  onAddTunnelPort?: (
    name: string,
    direction: 'input' | 'output',
    portFunction?: 'DATA' | 'CONTROL',
    valueType?: string,
  ) => Promise<void>,
  onRemoveTunnelPort?: (name: string, direction: 'input' | 'output') => Promise<void>,
  onRenameTunnelPort?: (oldName: string, newName: string, direction: 'input' | 'output') => Promise<void>,
): { nodes: FlowNode<NodeData>[]; edges: FlowEdge[] } {
  const nodes: FlowNode<NodeData>[] = network.nodes.map((n) => ({
    id: n.id,
    type:
      n.kind === 'NETWORK'
        ? 'networkNode'
        : n.kind === 'TUNNEL_INPUT' || n.type === 'TUNNEL_INPUT'
          ? 'tunnelInputNode'
          : n.kind === 'TUNNEL_OUTPUT' || n.type === 'TUNNEL_OUTPUT'
            ? 'tunnelOutputNode'
            : n.kind === 'SELF'
              ? 'tunnelInputNode'
              : 'functionNode',
    position: n.position,
    deletable: !(n.kind === 'TUNNEL_INPUT' || n.kind === 'TUNNEL_OUTPUT' || n.kind === 'SELF'),
    data: {
      label: n.name,
      nodeType: n.type,
      path: n.path,
      inputs: n.inputs,
      outputs: n.outputs,
      isFlowControlNode: n.isFlowControlNode,
      subnetworkId: n.subnetworkId,
      onEnter: n.subnetworkId ? (sid: string) => onEnter(sid, n.name) : undefined,
      // Tunnel port callbacks — only meaningful for SELF nodes, but harmless on others
      onAddTunnelPort,
      onRemoveTunnelPort,
      onRenameTunnelPort,
    },
  }));

  const edges: FlowEdge[] = network.edges.map((e) => ({
    id: e.id,
    source: e.sourceNodeId,
    sourceHandle: `out-${e.sourcePortName}`,
    target: e.targetNodeId,
    targetHandle: `in-${e.targetPortName}`,
    selectable: true,
    deletable: true,
    interactionWidth: 18,
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
          (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
          (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
          (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
          (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({ nodes, edges });
    },

    groupNodes: async (nodeIds) => {
      const { currentNetworkId, nodes: currentNodes } = get();
      if (!currentNetworkId || nodeIds.length === 0) return;
      const existingNodeIds = new Set(currentNodes.map((node) => node.id));
      const name = `subnet_${Math.random().toString(36).slice(2, 8)}`;
      const network = await graphClient.groupNodes(currentNetworkId, nodeIds, name);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({
        edges,
        nodes: nodes.map((node) => ({
          ...node,
          selected: node.type === 'networkNode' && !existingNodeIds.has(node.id),
        })),
      });
    },

    deleteNode: async (nodeId) => {
      const { currentNetworkId, nodes } = get();
      if (!currentNetworkId) return;
      const targetNode = nodes.find((node) => node.id === nodeId);
      if (targetNode?.deletable === false) return;
      await graphClient.deleteNode(currentNetworkId, nodeId);
      set((s) => ({
        nodes: s.nodes.filter((n) => n.id !== nodeId),
        edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      }));
    },

    renameNode: async (nodeId, name) => {
      const { currentNetworkId } = get();
      const nextName = name.trim();
      if (!currentNetworkId || !nextName) return;
      await graphClient.renameNode(currentNetworkId, nodeId, nextName);
      set((s) => ({
        nodes: s.nodes.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, label: nextName } }
            : node,
        ),
        breadcrumb: s.breadcrumb.map((entry) =>
          entry.id === nodeId ? { ...entry, name: nextName } : entry,
        ),
      }));
    },

    deleteEdge: async (edgeId) => {
      const { currentNetworkId, edges } = get();
      if (!currentNetworkId) return;
      const edge = edges.find((candidate) => candidate.id === edgeId);
      if (!edge) return;

      const sourcePort = edge.sourceHandle?.replace(/^out-/, '') ?? '';
      const targetPort = edge.targetHandle?.replace(/^in-/, '') ?? '';
      await graphClient.removeEdge(
        currentNetworkId,
        toGraphNodeId(edge.source),
        sourcePort,
        toGraphNodeId(edge.target),
        targetPort,
      );
      set((s) => ({
        edges: s.edges.filter((candidate) => candidate.id !== edgeId),
      }));
      await get().refreshNodes();
    },

    onConnect: async (connection) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId || !connection.source || !connection.target) return;
      const sourcePort = connection.sourceHandle?.replace('out-', '') ?? '';
      const targetPort = connection.targetHandle?.replace('in-', '') ?? '';
      const network = await graphClient.addEdge(
        currentNetworkId,
        toGraphNodeId(connection.source),
        sourcePort,
        toGraphNodeId(connection.target),
        targetPort,
      );
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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

    setSelection: (nodeIds, edgeIds) => {
      const selectedNodeIds = new Set(nodeIds);
      const selectedEdgeIds = new Set(edgeIds);
      set((s) => ({
        nodes: s.nodes.map((node) => ({
          ...node,
          selected: selectedNodeIds.has(node.id),
        })),
        edges: s.edges.map((edge) => ({
          ...edge,
          selected: selectedEdgeIds.has(edge.id),
        })),
      }));
    },

    saveSelection: async (name) => {
      const { currentNetworkId, nodes } = get();
      if (!currentNetworkId) return;
      const nodeIds = nodes
        .filter((node) => node.selected && node.deletable !== false)
        .map((node) => toGraphNodeId(node.id));
      await graphClient.saveSelection(name, currentNetworkId, nodeIds);
    },

    setPortValue: async (nodeId, portName, value) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.setPortValue(currentNetworkId, nodeId, portName, value);
      await get().refreshNodes();
    },

    addTunnelPort: async (name, direction, portFunction = 'DATA', valueType = 'ANY') => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const network = await graphClient.addTunnelPort(currentNetworkId, name, direction, portFunction, valueType);
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({ nodes, edges });
    },

    connectToNewTunnelInput: async (sourceNodeId, sourcePort) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const network = await graphClient.connectToNewTunnelInput(
        currentNetworkId,
        toGraphNodeId(sourceNodeId),
        sourcePort,
      );
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({ nodes, edges });
    },

    connectNewTunnelInputToTarget: async (targetNodeId, targetPort) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const network = await graphClient.connectNewTunnelInputToTarget(
        currentNetworkId,
        toGraphNodeId(targetNodeId),
        targetPort,
      );
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({ nodes, edges });
    },

    connectToNewTunnelOutput: async (sourceNodeId, sourcePort) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      const network = await graphClient.connectToNewTunnelOutput(
        currentNetworkId,
        toGraphNodeId(sourceNodeId),
        sourcePort,
      );
      const { nodes, edges } = networkToFlow(
        network,
        (sid, sname) => get().enterSubnetwork(sid, sname),
        (n, dir) => get().addTunnelPort(n, dir),
        (n, dir) => get().removeTunnelPort(n, dir),
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
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
        (oldName, newName, dir) => get().renameTunnelPort(oldName, newName, dir),
      );
      set({ nodes, edges });
    },

    renameTunnelPort: async (oldName, newName, direction) => {
      const { currentNetworkId } = get();
      if (!currentNetworkId) return;
      await graphClient.renameTunnelPort(currentNetworkId, oldName, newName, direction);
      await get().refreshNodes();
    },
  }));
}
