/**
 * GraphCanvas — the main ReactFlow editing surface.
 *
 * Features:
 * - Drag-and-drop node creation from the NodePalette sidebar
 * - Connect nodes by dragging between handles
 * - Marquee-select nodes by dragging on the empty canvas
 * - Group selected nodes into a subnetwork with Cmd+G
 * - Delete selected nodes via the Delete/Backspace key
 * - Enter subnetworks by clicking the ⤵ Enter button on NetworkNodes
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  ControlButton,
  MiniMap,
  useReactFlow,
  NodeChange,
  EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  Connection,
  FinalConnectionState,
  BackgroundVariant,
  Node as FlowNode,
  Edge as FlowEdge,
  NodeTypes,
  DefaultEdgeOptions,
  SelectionMode,
} from '@xyflow/react';
import { FunctionNode } from '../nodes/FunctionNode';
import { NetworkNode } from '../nodes/NetworkNode';
import { TunnelInputNode } from '../nodes/TunnelInputNode';
import { TunnelOutputNode } from '../nodes/TunnelOutputNode';
import { NodePalette } from './NodePalette';
import { ParameterPane } from './ParameterPane';
import type { SelectedNodeInfo } from './ParameterPane';
import { usePaneStore } from './PaneContext';
import type { NodeData } from '../../types/uiTypes';
import { useTraceStore } from '../../store/traceStore';

// ── Custom node type registry ─────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nodeTypes: NodeTypes = {
  functionNode: FunctionNode as any,
  networkNode: NetworkNode as any,
  tunnelInputNode: TunnelInputNode as any,
  tunnelOutputNode: TunnelOutputNode as any,
  tunnelNode: TunnelInputNode as any,
};

// Selection commits to the pane store are debounced so high-frequency marquee
// drags don't rebuild the entire nodes/edges arrays in the store on each
// pointer move. The visual selection feedback stays live via React Flow's
// internal state and our local copies.
const SELECTION_COMMIT_DELAY_MS = 80;

// Module-level constants so ReactFlow doesn't see new prop references every
// render. New references on these props can invalidate internal memoization
// inside ReactFlow during marquee drags.
const PRO_OPTIONS = { hideAttribution: true } as const;
const PAN_ON_DRAG: number[] = [0, 1, 2];
const DEFAULT_EDGE_OPTIONS: DefaultEdgeOptions = {
  style: { stroke: 'rgba(148, 163, 184, 0.5)', strokeWidth: 1.8 },
  animated: false,
};
const CONNECTION_LINE_STYLE = { stroke: '#5eead4', strokeWidth: 1.8 } as const;
const CONTROLS_STYLE = {
  background: 'rgba(15, 23, 42, 0.85)',
  border: '1px solid rgba(148, 163, 184, 0.14)',
  borderRadius: 10,
} as const;
const MINIMAP_STYLE = {
  background: 'rgba(2, 6, 23, 0.85)',
  border: '1px solid rgba(148, 163, 184, 0.14)',
  borderRadius: 10,
} as const;
const ACTIVE_EDGE_STYLE = { stroke: '#facc15', strokeWidth: 2.6 } as const;
const IDLE_EDGE_STYLE = { stroke: 'rgba(148, 163, 184, 0.38)', strokeWidth: 1.6 } as const;
const GROUP_BUTTON_ACTIVE_STYLE = { opacity: 1, cursor: 'pointer' } as const;
const GROUP_BUTTON_INACTIVE_STYLE = { opacity: 0.45, cursor: 'not-allowed' } as const;

// Compare nodes/edges arrays by their structural fields, ignoring `selected`.
// Used to skip the store→local re-sync that runs after our debounced selection
// commits — the local state already reflects the latest selection, so copying
// the store's "newly committed" selection back into local state would only
// trigger a redundant whole-canvas re-render.
function nodesStructurallyEqual(
  a: FlowNode<NodeData>[],
  b: FlowNode<NodeData>[],
): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const na = a[i];
    const nb = b[i];
    if (
      na.id !== nb.id ||
      na.type !== nb.type ||
      na.position !== nb.position ||
      na.data !== nb.data ||
      na.deletable !== nb.deletable
    ) {
      return false;
    }
  }
  return true;
}

function edgesStructurallyEqual(a: FlowEdge[], b: FlowEdge[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const ea = a[i];
    const eb = b[i];
    if (
      ea.id !== eb.id ||
      ea.source !== eb.source ||
      ea.target !== eb.target ||
      ea.sourceHandle !== eb.sourceHandle ||
      ea.targetHandle !== eb.targetHandle
    ) {
      return false;
    }
  }
  return true;
}

function eventPoint(event: MouseEvent | TouchEvent): { x: number; y: number } | null {
  if ('changedTouches' in event) {
    const touch = event.changedTouches[0];
    return touch ? { x: touch.clientX, y: touch.clientY } : null;
  }
  return { x: event.clientX, y: event.clientY };
}

// ── Main canvas ───────────────────────────────────────────────────────────────

function FlowCanvas() {
  const { screenToFlowPosition, fitView } = useReactFlow();
  const nodes = usePaneStore((s) => s.nodes);
  const edges = usePaneStore((s) => s.edges);
  const createNode = usePaneStore((s) => s.createNode);
  const createSubnetwork = usePaneStore((s) => s.createSubnetwork);
  const groupNodes = usePaneStore((s) => s.groupNodes);
  const deleteNode = usePaneStore((s) => s.deleteNode);
  const deleteEdge = usePaneStore((s) => s.deleteEdge);
  const onConnect = usePaneStore((s) => s.onConnect);
  const connectToNewTunnelInput = usePaneStore((s) => s.connectToNewTunnelInput);
  const connectNewTunnelInputToTarget = usePaneStore((s) => s.connectNewTunnelInputToTarget);
  const connectToNewTunnelOutput = usePaneStore((s) => s.connectToNewTunnelOutput);
  const persistPosition = usePaneStore((s) => s.onNodesChange);
  const setSelection = usePaneStore((s) => s.setSelection);

  // Local copy so ReactFlow can move nodes immediately without waiting for the server
  const [localNodes, setLocalNodes] = useState<FlowNode<NodeData>[]>(nodes);
  const [localEdges, setLocalEdges] = useState<FlowEdge[]>(edges);
  const localNodesRef = useRef(localNodes);
  const localEdgesRef = useRef(localEdges);
  const selectionCommitTimerRef = useRef<number | null>(null);
  const latestSelectionRef = useRef<{ nodeIds: string[]; edgeIds: string[] }>({
    nodeIds: [],
    edgeIds: [],
  });

  // Track active node drags so we can hide the live MiniMap (which subscribes
  // to React Flow's internal node store and would otherwise re-render on every
  // pointer move during a drag).
  const [isDraggingNodes, setIsDraggingNodes] = useState(false);
  const handleNodeDragStart = useCallback(() => setIsDraggingNodes(true), []);
  const handleNodeDragStop = useCallback(() => setIsDraggingNodes(false), []);

  // Selection-derived flags that the toolbar/inspector consume. We update
  // them only when a `select` change actually fires, so a pure position drag
  // does not re-render the surrounding UI.
  const [hasGroupableSelection, setHasGroupableSelection] = useState(false);
  const [primarySelectedNode, setPrimarySelectedNode] = useState<FlowNode<NodeData> | null>(null);

  const refreshSelectionFlags = useCallback(
    (nextNodes: FlowNode<NodeData>[]) => {
      const groupable = nextNodes.some((n) => n.selected && n.deletable !== false);
      setHasGroupableSelection((prev) => (prev === groupable ? prev : groupable));
      const next = nextNodes.find((n) => n.selected) ?? null;
      setPrimarySelectedNode((prev) => {
        if (!next) return prev === null ? prev : null;
        if (prev && prev.id === next.id && prev.data === next.data && prev.type === next.type) {
          return prev;
        }
        return next;
      });
    },
    [],
  );

  // Sync from store whenever remote state changes. Skip selection-only
  // updates: when our debounced selection commit writes selection back into
  // the pane store, it produces a new `nodes`/`edges` array reference but the
  // structural fields are unchanged. Re-applying that reference here would
  // re-render the entire canvas (and the MiniMap via React Flow's internal
  // store) for no visible benefit, since our local state already shows the
  // correct selection.
  useEffect(() => {
    if (nodesStructurallyEqual(localNodesRef.current, nodes)) return;
    localNodesRef.current = nodes;
    setLocalNodes(nodes);
    refreshSelectionFlags(nodes);
  }, [nodes, refreshSelectionFlags]);
  useEffect(() => {
    if (edgesStructurallyEqual(localEdgesRef.current, edges)) return;
    localEdgesRef.current = edges;
    setLocalEdges(edges);
  }, [edges]);

  const scheduleSelectionCommit = useCallback(
    (nextNodes: FlowNode<NodeData>[], nextEdges: FlowEdge[]) => {
      latestSelectionRef.current = {
        nodeIds: nextNodes.filter((node) => node.selected).map((node) => node.id),
        edgeIds: nextEdges.filter((edge) => edge.selected).map((edge) => edge.id),
      };

      if (selectionCommitTimerRef.current !== null) {
        window.clearTimeout(selectionCommitTimerRef.current);
      }

      selectionCommitTimerRef.current = window.setTimeout(() => {
        selectionCommitTimerRef.current = null;
        const { nodeIds, edgeIds } = latestSelectionRef.current;
        setSelection(nodeIds, edgeIds);
      }, SELECTION_COMMIT_DELAY_MS);
    },
    [setSelection],
  );

  useEffect(
    () => () => {
      if (selectionCommitTimerRef.current !== null) {
        window.clearTimeout(selectionCommitTimerRef.current);
      }
    },
    [],
  );

  // Handle node changes locally; persist on drag end. We must apply every
  // change (including per-frame `position` deltas while dragging) because
  // React Flow runs in controlled mode and uses the prop value to drive the
  // drag visuals — skipping per-frame updates makes drag feel laggy.
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const hasSelectChange = changes.some((c) => c.type === 'select');
      setLocalNodes((ns) => {
        const nextNodes = applyNodeChanges(changes, ns) as FlowNode<NodeData>[];
        localNodesRef.current = nextNodes;
        if (hasSelectChange) {
          scheduleSelectionCommit(nextNodes, localEdgesRef.current);
          refreshSelectionFlags(nextNodes);
        }
        return nextNodes;
      });
      for (const c of changes) {
        if (c.type === 'position' && !c.dragging && c.position) {
          persistPosition(c.id, c.position.x, c.position.y);
        }
      }
    },
    [persistPosition, scheduleSelectionCommit, refreshSelectionFlags],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setLocalEdges((es) => {
        const nextEdges = applyEdgeChanges(changes, es);
        localEdgesRef.current = nextEdges;
        if (changes.some((c) => c.type === 'select')) {
          scheduleSelectionCommit(localNodesRef.current, nextEdges);
        }
        return nextEdges;
      });
    },
    [scheduleSelectionCommit],
  );

  const handleConnect = useCallback(
    (conn: Connection) => onConnect(conn),
    [onConnect],
  );

  const handleConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent, connectionState: FinalConnectionState) => {
      const point = eventPoint(event);
      if (!point || !connectionState.fromHandle?.nodeId || !connectionState.fromHandle.id) return;

      const dropElement = document
        .elementFromPoint(point.x, point.y)
        ?.closest<HTMLElement>('[data-tunnel-add-zone]');
      const direction = dropElement?.dataset.tunnelAddZone;
      if (direction !== 'input' && direction !== 'output') return;

      const { fromHandle } = connectionState;
      const portName = fromHandle.id.replace(/^out-/, '').replace(/^in-/, '');
      if (!portName) return;

      if (direction === 'input') {
        if (fromHandle.type === 'target') {
          connectNewTunnelInputToTarget(fromHandle.nodeId, portName);
        } else {
          connectToNewTunnelInput(fromHandle.nodeId, portName);
        }
      } else if (fromHandle.type === 'source') {
        connectToNewTunnelOutput(fromHandle.nodeId, portName);
      }
    },
    [connectNewTunnelInputToTarget, connectToNewTunnelInput, connectToNewTunnelOutput],
  );

  // We intentionally do NOT derive selectedNodes/selectedEdges/etc. from
  // `localNodes` directly with `useMemo`, because `localNodes` gets a new
  // reference on every drag frame (positions update). Re-deriving every frame
  // would invalidate consumers (Controls buttons, ParameterPane, the
  // wrapping `onKeyDown` listener) and cause a full subtree re-render.
  // Instead, callbacks read the latest state from the refs at call-time, and
  // selection-derived UI flags are tracked as separate state only updated on
  // `select` changes.
  const handleHome = useCallback(() => {
    const selected = localNodesRef.current.filter((n) => n.selected);
    if (selected.length > 0) {
      fitView({ nodes: selected, padding: 0.35, duration: 350, maxZoom: 1.5 });
    } else {
      fitView({ padding: 0.1, duration: 350 });
    }
  }, [fitView]);

  const handleGroupSelected = useCallback(() => {
    const groupable = localNodesRef.current.filter(
      (n) => n.selected && n.deletable !== false,
    );
    if (groupable.length === 0) return;
    void groupNodes(groupable.map((node) => node.id));
  }, [groupNodes]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key.toLowerCase() === 'g' && e.metaKey) {
        const groupable = localNodesRef.current.filter(
          (n) => n.selected && n.deletable !== false,
        );
        if (groupable.length > 0) {
          e.preventDefault();
          e.stopPropagation();
          handleGroupSelected();
        }
        return;
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        const sNodes = localNodesRef.current.filter(
          (n) => n.selected && n.deletable !== false,
        );
        const sEdges = localEdgesRef.current.filter((edge) => edge.selected);
        if (sNodes.length > 0 || sEdges.length > 0) {
          e.preventDefault();
          e.stopPropagation();
          void (async () => {
            for (const edge of sEdges) await deleteEdge(edge.id);
            for (const node of sNodes) await deleteNode(node.id);
          })();
        }
      }
      if (e.key === 'h' || e.key === 'H') {
        handleHome();
      }
    },
    [deleteEdge, deleteNode, handleHome, handleGroupSelected],
  );

  // ── Palette callbacks ──────────────────────────────────────────────────────

  // Click + in palette → place at canvas centre
  const handleAddNode = useCallback(
    (type: string) => {
      const position = screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
      createNode(type, position);
    },
    [screenToFlowPosition, createNode],
  );

  const handleAddSubnetwork = useCallback(
    (name: string) => {
      const position = screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
      createSubnetwork(name, position);
    },
    [screenToFlowPosition, createSubnetwork],
  );

  // ── Drag-and-drop from palette ─────────────────────────────────────────────

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes('application/nodegraph-type')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData('application/nodegraph-type');
      if (!type) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      createNode(type, position);
    },
    [screenToFlowPosition, createNode],
  );

  // ── Selection → inspector ──────────────────────────────────────────────────

  // Built from the dedicated `primarySelectedNode` state so that the inspector
  // is only rebuilt when selection or node data actually changes — not on
  // every drag frame, which would otherwise force ParameterPane to re-render
  // continuously.
  const selectedInfo: SelectedNodeInfo | null = useMemo(() => {
    if (!primarySelectedNode) return null;
    return {
      id: primarySelectedNode.id,
      flowType: primarySelectedNode.type ?? 'functionNode',
      label: primarySelectedNode.data.label,
      inputs: primarySelectedNode.data.inputs,
      outputs: primarySelectedNode.data.outputs,
      isFlowControlNode: primarySelectedNode.data.isFlowControlNode,
      subnetworkId: primarySelectedNode.data.subnetworkId,
    };
  }, [primarySelectedNode]);

  // ── Trace edge highlighting ────────────────────────────────────────────────
  // Serialize active edges to a stable string so this component only re-renders
  // when the *set* of animated edges actually changes, not on every other trace
  // event (nodeStates updates, etc.).
  const activeEdgeSerial = useTraceStore((s) => {
    const now = Date.now();
    return s.activeEdges
      .filter((e) => e.expiresAt > now)
      .map((e) => `${e.fromNodeId}:${e.toNodeId}`)
      .sort()
      .join('|');
  });
  const nodeStateSerial = useTraceStore((s) =>
    Object.entries(s.nodeStates)
      .map(([nodeId, info]) => `${nodeId}:${info.state}`)
      .sort()
      .join('|'),
  );

  const nodeStateMap = useMemo(() => {
    const map = new Map<string, string>();
    if (!nodeStateSerial) return map;
    for (const pair of nodeStateSerial.split('|')) {
      const [nodeId, state] = pair.split(':');
      if (nodeId && state) map.set(nodeId, state);
    }
    return map;
  }, [nodeStateSerial]);

  // Skip rebuilding edge objects entirely when no edges are highlighted. This
  // preserves array + object identity across selection-only changes, which
  // means React Flow's internal edge memoization can fully bail out.
  const highlightedEdges = useMemo(() => {
    if (!activeEdgeSerial) return localEdges;
    const activeSet = new Set(activeEdgeSerial.split('|'));
    return localEdges.map((edge) => {
      const isActive = activeSet.has(`${edge.source}:${edge.target}`);
      return isActive
        ? { ...edge, animated: false, style: ACTIVE_EDGE_STYLE }
        : { ...edge, style: IDLE_EDGE_STYLE };
    });
  }, [localEdges, activeEdgeSerial]);

  // ── Refresh inspector when execution pauses at a new node or run completes ──
  const refreshNodes = usePaneStore((s) => s.refreshNodes);
  const setPortValue = usePaneStore((s) => s.setPortValue);
  const pausedAtNodeId = useTraceStore((s) => s.pausedAtNodeId);
  const isRunning     = useTraceStore((s) => s.isRunning);
  const prevPausedRef  = useRef<string | null>(null);
  const wasRunningRef  = useRef(false);

  useEffect(() => {
    // A new STEP_PAUSE arrived — previous node has finished, its outputs are ready
    if (pausedAtNodeId !== null && pausedAtNodeId !== prevPausedRef.current) {
      refreshNodes();
    }
    prevPausedRef.current = pausedAtNodeId;
  }, [pausedAtNodeId, refreshNodes]);

  useEffect(() => {
    // Execution just finished — refresh to show final output values
    if (wasRunningRef.current && !isRunning) {
      refreshNodes();
    }
    wasRunningRef.current = isRunning;
  }, [isRunning, refreshNodes]);

  // Stable nodeColor for the MiniMap. Only changes when trace node-state map
  // changes, so the MiniMap doesn't see a fresh callback identity on every
  // selection-driven render.
  const minimapNodeColor = useCallback(
    (n: FlowNode) => {
      const state = nodeStateMap.get(n.id);
      if (state === 'error') return '#f87171';
      if (state === 'running' || state === 'pending') return '#facc15';
      if (state === 'waiting') return '#a78bfa';
      if (state === 'paused') return '#f97316';
      if (state === 'done') return '#4ade80';
      if (n.type === 'networkNode') return '#a78bfa';
      if (n.type === 'tunnelInputNode') return '#22d3ee';
      if (n.type === 'tunnelOutputNode') return '#f59e0b';
      return '#5eead4';
    },
    [nodeStateMap],
  );

  return (
    <div
      className="flex flex-1 overflow-hidden"
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <NodePalette onAddNode={handleAddNode} onAddSubnetwork={handleAddSubnetwork} />

      <div
        className="flex-1 relative"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <ReactFlow
          nodes={localNodes}
          edges={highlightedEdges}
          nodeTypes={nodeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          onConnectEnd={handleConnectEnd}
          onNodeDragStart={handleNodeDragStart}
          onNodeDragStop={handleNodeDragStop}
          onSelectionDragStart={handleNodeDragStart}
          onSelectionDragStop={handleNodeDragStop}
          deleteKeyCode={null}
          selectionOnDrag={false}
          selectionKeyCode="Shift"
          selectionMode={SelectionMode.Partial}
          panOnDrag={PAN_ON_DRAG}
          fitView
          onlyRenderVisibleElements
          proOptions={PRO_OPTIONS}
          defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
          connectionLineStyle={CONNECTION_LINE_STYLE}
        >
          <Background
            color="rgba(148, 163, 184, 0.14)"
            gap={28}
            size={1.2}
            variant={BackgroundVariant.Dots}
          />
          <Controls style={CONTROLS_STYLE}>
            <ControlButton
              onClick={handleHome}
              title="Home — fit selected nodes (or all nodes if none selected)  [H]"
            >
              ⌂
            </ControlButton>
            <ControlButton
              onClick={handleGroupSelected}
              title="Create subnetwork from selected nodes  [Cmd+G]"
              style={hasGroupableSelection ? GROUP_BUTTON_ACTIVE_STYLE : GROUP_BUTTON_INACTIVE_STYLE}
            >
              Group
            </ControlButton>
          </Controls>
          {!isDraggingNodes && (
            <MiniMap
              style={MINIMAP_STYLE}
              nodeColor={minimapNodeColor}
              maskColor="rgba(2, 6, 23, 0.55)"
              nodeStrokeColor="rgba(148, 163, 184, 0.3)"
            />
          )}
        </ReactFlow>
      </div>

      <ParameterPane selected={selectedInfo} onSetPortValue={setPortValue} />
    </div>
  );
}

export function GraphCanvas() {
  return <FlowCanvas />;
}
