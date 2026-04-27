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
import React, { useCallback, useEffect, useMemo, useRef } from 'react';
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
  NodeTypes,
  DefaultEdgeOptions,
  SelectionMode,
} from '@xyflow/react';
import { useState } from 'react';
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
  const [localEdges, setLocalEdges] = useState(edges);

  // Sync from store whenever remote state changes
  useEffect(() => { setLocalNodes(nodes); }, [nodes]);
  useEffect(() => { setLocalEdges(edges); }, [edges]);

  // Handle node moves locally; persist on drag end
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setLocalNodes((ns) => {
        const nextNodes = applyNodeChanges(changes, ns) as FlowNode<NodeData>[];
        if (changes.some((c) => c.type === 'select')) {
          setSelection(
            nextNodes.filter((node) => node.selected).map((node) => node.id),
            localEdges.filter((edge) => edge.selected).map((edge) => edge.id),
          );
        }
        return nextNodes;
      });
      for (const c of changes) {
        if (c.type === 'position' && !c.dragging && c.position) {
          persistPosition(c.id, c.position.x, c.position.y);
        }
      }
    },
    [persistPosition, setSelection, localEdges],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setLocalEdges((es) => {
        const nextEdges = applyEdgeChanges(changes, es);
        if (changes.some((c) => c.type === 'select')) {
          setSelection(
            localNodes.filter((node) => node.selected).map((node) => node.id),
            nextEdges.filter((edge) => edge.selected).map((edge) => edge.id),
          );
        }
        return nextEdges;
      });
    },
    [setSelection, localNodes],
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

  const handleHome = useCallback(() => {
    const selected = localNodes.filter((n) => n.selected);
    if (selected.length > 0) {
      fitView({ nodes: selected, padding: 0.35, duration: 350, maxZoom: 1.5 });
    } else {
      fitView({ padding: 0.1, duration: 350 });
    }
  }, [localNodes, fitView]);

  const groupableSelectedNodes = localNodes.filter((node) => node.selected && node.deletable !== false);

  const handleGroupSelected = useCallback(() => {
    if (groupableSelectedNodes.length === 0) return;
    void groupNodes(groupableSelectedNodes.map((node) => node.id));
  }, [groupNodes, groupableSelectedNodes]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key.toLowerCase() === 'g' && e.metaKey) {
        if (groupableSelectedNodes.length > 0) {
          e.preventDefault();
          e.stopPropagation();
          handleGroupSelected();
        }
        return;
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        const selectedNodes = localNodes.filter((n) => n.selected && n.deletable !== false);
        const selectedEdges = localEdges.filter((edge) => edge.selected);
        if (selectedNodes.length > 0 || selectedEdges.length > 0) {
          e.preventDefault();
          e.stopPropagation();
          void (async () => {
            for (const edge of selectedEdges) await deleteEdge(edge.id);
            for (const node of selectedNodes) await deleteNode(node.id);
          })();
        }
      }
      if (e.key === 'h' || e.key === 'H') {
        handleHome();
      }
    },
    [localNodes, localEdges, deleteEdge, deleteNode, handleHome, handleGroupSelected, groupableSelectedNodes],
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

  const selectedNode = localNodes.find((n) => n.selected) ?? null;
  const selectedInfo: SelectedNodeInfo | null = selectedNode
    ? {
        id: selectedNode.id,
        flowType: selectedNode.type ?? 'functionNode',
        label: selectedNode.data.label,
        inputs: selectedNode.data.inputs,
        outputs: selectedNode.data.outputs,
        isFlowControlNode: selectedNode.data.isFlowControlNode,
        subnetworkId: selectedNode.data.subnetworkId,
      }
    : null;

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

  const highlightedEdges = useMemo(() => {
    const activeSet = new Set(
      activeEdgeSerial ? activeEdgeSerial.split('|') : [],
    );
    return localEdges.map((edge) => {
      const isActive = activeSet.has(`${edge.source}:${edge.target}`);
      return isActive
        ? { ...edge, animated: false, style: { ...edge.style, stroke: '#facc15', strokeWidth: 2.6 } }
        : { ...edge, style: { ...edge.style, stroke: 'rgba(148, 163, 184, 0.38)', strokeWidth: 1.6 } };
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
          deleteKeyCode={null}
          selectionOnDrag={false}
          selectionKeyCode="Shift"
          selectionMode={SelectionMode.Partial}
          panOnDrag={[0, 1, 2]}
          fitView
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{
            style: { stroke: 'rgba(148, 163, 184, 0.5)', strokeWidth: 1.8 },
            animated: false,
          } as DefaultEdgeOptions}
          connectionLineStyle={{ stroke: '#5eead4', strokeWidth: 1.8 }}
        >
          <Background
            color="rgba(148, 163, 184, 0.14)"
            gap={28}
            size={1.2}
            variant={BackgroundVariant.Dots}
          />
          <Controls
            style={{
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(148, 163, 184, 0.14)',
              borderRadius: 10,
            }}
          >
            <ControlButton
              onClick={handleHome}
              title="Home — fit selected nodes (or all nodes if none selected)  [H]"
            >
              ⌂
            </ControlButton>
            <ControlButton
              onClick={handleGroupSelected}
              title="Create subnetwork from selected nodes  [Cmd+G]"
              style={{
                opacity: groupableSelectedNodes.length > 0 ? 1 : 0.45,
                cursor: groupableSelectedNodes.length > 0 ? 'pointer' : 'not-allowed',
              }}
            >
              Group
            </ControlButton>
          </Controls>
          <MiniMap
            style={{
              background: 'rgba(2, 6, 23, 0.85)',
              border: '1px solid rgba(148, 163, 184, 0.14)',
              borderRadius: 10,
            }}
            nodeColor={(n) => {
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
            }}
            maskColor="rgba(2, 6, 23, 0.55)"
            nodeStrokeColor="rgba(148, 163, 184, 0.3)"
          />
        </ReactFlow>
      </div>

      <ParameterPane selected={selectedInfo} onSetPortValue={setPortValue} />
    </div>
  );
}

export function GraphCanvas() {
  return <FlowCanvas />;
}
