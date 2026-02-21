/**
 * GraphCanvas — the main ReactFlow editing surface.
 *
 * Features:
 * - Drag-and-drop node creation from the NodePalette sidebar
 * - Connect nodes by dragging between handles
 * - Delete nodes via the Delete/Backspace key
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
  BackgroundVariant,
  Node as FlowNode,
  NodeTypes,
  DefaultEdgeOptions,
} from '@xyflow/react';
import { useState } from 'react';
import { FunctionNode } from '../nodes/FunctionNode';
import { NetworkNode } from '../nodes/NetworkNode';
import { TunnelInputNode } from '../nodes/TunnelInputNode';
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
  tunnelNode: TunnelInputNode as any,
};

// ── Main canvas ───────────────────────────────────────────────────────────────

function FlowCanvas() {
  const { screenToFlowPosition, fitView } = useReactFlow();
  const nodes = usePaneStore((s) => s.nodes);
  const edges = usePaneStore((s) => s.edges);
  const createNode = usePaneStore((s) => s.createNode);
  const createSubnetwork = usePaneStore((s) => s.createSubnetwork);
  const deleteNode = usePaneStore((s) => s.deleteNode);
  const onConnect = usePaneStore((s) => s.onConnect);
  const persistPosition = usePaneStore((s) => s.onNodesChange);

  // Local copy so ReactFlow can move nodes immediately without waiting for the server
  const [localNodes, setLocalNodes] = useState<FlowNode<NodeData>[]>(nodes);
  const [localEdges, setLocalEdges] = useState(edges);

  // Sync from store whenever remote state changes
  useEffect(() => { setLocalNodes(nodes); }, [nodes]);
  useEffect(() => { setLocalEdges(edges); }, [edges]);

  // Handle node moves locally; persist on drag end
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setLocalNodes((ns) => applyNodeChanges(changes, ns) as FlowNode<NodeData>[]);
      for (const c of changes) {
        if (c.type === 'position' && !c.dragging && c.position) {
          persistPosition(c.id, c.position.x, c.position.y);
        }
      }
    },
    [persistPosition],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => setLocalEdges((es) => applyEdgeChanges(changes, es)),
    [],
  );

  const handleConnect = useCallback(
    (conn: Connection) => onConnect(conn),
    [onConnect],
  );

  const handleHome = useCallback(() => {
    const selected = localNodes.filter((n) => n.selected);
    if (selected.length > 0) {
      fitView({ nodes: selected, padding: 0.35, duration: 350, maxZoom: 1.5 });
    } else {
      fitView({ padding: 0.1, duration: 350 });
    }
  }, [localNodes, fitView]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const selected = localNodes.filter((n) => n.selected);
        for (const n of selected) deleteNode(n.id);
      }
      if (e.key === 'h' || e.key === 'H') {
        handleHome();
      }
    },
    [localNodes, deleteNode, handleHome],
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

  // ── Trace edge animation ───────────────────────────────────────────────────
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

  const animatedEdges = useMemo(() => {
    const activeSet = new Set(
      activeEdgeSerial ? activeEdgeSerial.split('|') : [],
    );
    return localEdges.map((edge) => {
      const isActive = activeSet.has(`${edge.source}:${edge.target}`);
      return isActive
        ? { ...edge, animated: true, style: { ...edge.style, stroke: '#facc15', strokeWidth: 2 } }
        : edge;
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
      style={{ display: 'flex', flex: 1, overflow: 'hidden' }}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <NodePalette onAddNode={handleAddNode} onAddSubnetwork={handleAddSubnetwork} />

      <div
        style={{ flex: 1, position: 'relative' }}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <ReactFlow
          nodes={localNodes}
          edges={animatedEdges}
          nodeTypes={nodeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          fitView
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{
            style: { stroke: '#4b5280', strokeWidth: 2 },
            animated: false,
          } as DefaultEdgeOptions}
          connectionLineStyle={{ stroke: '#6d7de8', strokeWidth: 2 }}
        >
          <Background
            color="#252840"
            gap={24}
            size={1.5}
            variant={BackgroundVariant.Dots}
            style={{ background: '#11121c' }}
          />
          <Controls
            style={{
              background: '#13141f',
              border: '1px solid #2c2f45',
              borderRadius: 8,
            }}
          >
            <ControlButton
              onClick={handleHome}
              title="Home — fit selected nodes (or all nodes if none selected)  [H]"
            >
              ⌂
            </ControlButton>
          </Controls>
          <MiniMap
            style={{
              background: '#13141f',
              border: '1px solid #2c2f45',
              borderRadius: 8,
            }}
            nodeColor={(n) => n.type === 'networkNode' ? '#a78bfa' : '#6d7de8'}
            maskColor="rgba(13,14,25,0.75)"
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
