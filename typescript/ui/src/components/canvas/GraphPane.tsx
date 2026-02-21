/**
 * GraphPane — a self-contained graph editing pane.
 *
 * Each pane owns its own navigation state (current network, breadcrumb)
 * via a per-pane store, allowing independent exploration in split-view.
 */
import React, { useEffect, useMemo } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { PaneContext, usePaneStore } from './PaneContext';
import { BreadcrumbNav } from './BreadcrumbNav';
import { GraphCanvas } from './GraphCanvas';
import { useGraphStore } from '../../store/graphStore';
import { useTraceStore } from '../../store/traceStore';
import type { PaneStore } from '../../store/paneStore';

// ── Inner component (has PaneContext available) ────────────────────────────────

function PaneInner({
  paneIndex,
  onClose,
}: {
  paneIndex: number;
  onClose?: () => void;
}) {
  const { rootNetworkId, rootNetworkName } = useGraphStore((s) => ({
    rootNetworkId: s.rootNetworkId,
    rootNetworkName: s.rootNetworkName,
  }));
  const loadNetwork      = usePaneStore((s) => s.loadNetwork);
  const breadcrumb       = usePaneStore((s) => s.breadcrumb);
  const paneLoading      = usePaneStore((s) => s.paneLoading);
  const nodes            = usePaneStore((s) => s.nodes);
  const enterSubnetwork  = usePaneStore((s) => s.enterSubnetwork);
  const exitTo           = usePaneStore((s) => s.exitTo);

  // Trace state for step-navigation buttons
  const { isPaused, pausedAtNodeId } = useTraceStore((s) => ({
    isPaused:       s.isPaused,
    pausedAtNodeId: s.pausedAtNodeId,
  }));

  // Load root when this pane mounts (or when global init resolves)
  useEffect(() => {
    if (rootNetworkId && breadcrumb.length === 0) {
      loadNetwork(rootNetworkId, rootNetworkName);
    }
  }, [rootNetworkId]);

  // Identify if the paused (or selected) node in THIS pane is a NetworkNode.
  // The "step into" button is available if any visible NetworkNode is selected OR
  // if the current STEP_PAUSE landed on a NetworkNode in this pane.
  const stepIntoTarget = useMemo(() => {
    // Prefer the paused node first, then the selected node
    const candidates = pausedAtNodeId
      ? nodes.filter((n) => n.id === pausedAtNodeId)
      : nodes.filter((n) => n.selected);
    const networkNode = candidates.find(
      (n) => n.type === 'networkNode' && (n.data as any).subnetworkId,
    );
    if (!networkNode) return null;
    return {
      subnetworkId: (networkNode.data as any).subnetworkId as string,
      label: (networkNode.data as any).label as string,
    };
  }, [nodes, pausedAtNodeId]);

  // "Step Out" is available whenever we are inside a subnetwork
  const canStepOut = breadcrumb.length > 1;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        overflow: 'hidden',
        minWidth: 0,
      }}
    >
      {/* Per-pane header: breadcrumb + pane controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          height: 32,
          background: '#11111b',
          borderBottom: '1px solid #2c2f45',
          paddingLeft: 8,
          flexShrink: 0,
          gap: 4,
        }}
      >
        {/* Pane index badge */}
        <span
          style={{
            fontFamily: 'monospace',
            fontSize: 9,
            color: '#535677',
            border: '1px solid #2c2f45',
            borderRadius: 3,
            padding: '1px 5px',
            flexShrink: 0,
          }}
        >
          {paneIndex + 1}
        </span>

        {/* Breadcrumb */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <BreadcrumbNav />
        </div>

        {/* ── Step Out button ─────────────────────────────────────────────── */}
        {canStepOut && (
          <button
            onClick={() => exitTo(breadcrumb.length - 2)}
            title={`Navigate out to "${breadcrumb[breadcrumb.length - 2]?.name}"`}
            style={{
              background: 'none',
              border: '1px solid #4b5280',
              borderRadius: 4,
              color: '#9ea3c0',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: 10,
              padding: '2px 7px',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = '#1e2133';
              (e.currentTarget as HTMLElement).style.color = '#c9cce8';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = 'none';
              (e.currentTarget as HTMLElement).style.color = '#9ea3c0';
            }}
          >
            ⤴ Out
          </button>
        )}

        {/* ── Step Into button ────────────────────────────────────────────── */}
        {stepIntoTarget && (
          <button
            onClick={() => enterSubnetwork(stepIntoTarget.subnetworkId, stepIntoTarget.label)}
            title={`Enter subnetwork "${stepIntoTarget.label}"`}
            style={{
              background: isPaused ? 'rgba(249,115,22,0.15)' : 'none',
              border: `1px solid ${isPaused ? '#f97316' : '#4b5280'}`,
              borderRadius: 4,
              color: isPaused ? '#f97316' : '#9ea3c0',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: 10,
              padding: '2px 7px',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = isPaused
                ? 'rgba(249,115,22,0.3)'
                : '#1e2133';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = isPaused
                ? 'rgba(249,115,22,0.15)'
                : 'none';
            }}
          >
            ⤵ {stepIntoTarget.label}
          </button>
        )}

        {/* Loading indicator */}
        {paneLoading && (
          <span
            style={{
              fontFamily: 'monospace',
              fontSize: 9,
              color: '#fab387',
              flexShrink: 0,
              paddingRight: 6,
            }}
          >
            ···
          </span>
        )}

        {/* Close pane button */}
        {onClose && (
          <button
            onClick={onClose}
            title="Close this pane"
            style={{
              background: 'none',
              border: 'none',
              color: '#535677',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: 13,
              lineHeight: 1,
              padding: '0 6px',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = '#f38ba8')}
            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = '#535677')}
          >
            ✕
          </button>
        )}
      </div>

      {/* Canvas (palette + flow + inspector) */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        <GraphCanvas />
      </div>
    </div>
  );
}

// ── Public component ───────────────────────────────────────────────────────────

export function GraphPane({
  store,
  paneIndex,
  onClose,
}: {
  store: PaneStore;
  paneIndex: number;
  onClose?: () => void;
}) {
  return (
    <PaneContext.Provider value={store}>
      <ReactFlowProvider>
        <PaneInner paneIndex={paneIndex} onClose={onClose} />
      </ReactFlowProvider>
    </PaneContext.Provider>
  );
}
