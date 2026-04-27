/**
 * NetworkNode — n8n/Griptape-inspired card node for subnetwork containers.
 * Visually distinct from FunctionNode via a violet accent + dashed border.
 */
import React, { useCallback, useState } from 'react';
import { Handle, Position, NodeProps, Node } from '@xyflow/react';
import type { NodeData, SerializedPort } from '../../types/uiTypes';
import { usePaneStore } from '../canvas/PaneContext';
import { PortValueRenderer } from './PortValueRenderer';
import { useTraceStore } from '../../store/traceStore';
import { EditableNodeTitle } from './EditableNodeTitle';
import {
  StatusBadge,
  PortColumnHeader,
  getNodeVisualState,
  headerActionStyle,
  nodeAccentRailStyle,
  nodeCardClassName,
  nodeCardStyle,
} from './nodeVisuals';

// ── Trace glow colours ────────────────────────────────────────────────────────

// ── Design tokens ─────────────────────────────────────────────────────────────

// Semantic colours for network (violet) / control (pink) port handles
const NET_COL   = '#c084fc';
const CTRL_COL  = '#f472b6';
const ACCENT    = NET_COL;

// CSS variable shorthands for runtime theme
const CV = {
  bg:        'var(--card)',
  border:    'var(--border)',
  text:      'var(--foreground)',
  muted:     'var(--muted-foreground)',
  portHov:   'rgba(148, 163, 184, 0.10)',
};

// ── Value-type chip (same palette as FunctionNode) ─────────────────────────────

const CHIP_COLORS: Record<string, [string, string]> = {
  int:    ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  float:  ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  number: ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  str:    ['rgba(74, 222, 128, 0.14)', '#86efac'],
  string: ['rgba(74, 222, 128, 0.14)', '#86efac'],
  bool:   ['rgba(250, 204, 21, 0.14)', '#fde047'],
  any:    ['rgba(192, 132, 252, 0.12)', NET_COL],
};

function ValueChip({ vt }: { vt: string }) {
  const [bg, fg] = CHIP_COLORS[vt.toLowerCase()] ?? CHIP_COLORS.any;
  return (
    <span
      style={{
        background: bg,
        color: fg,
        fontSize: 9,
        fontWeight: 700,
        padding: '2px 7px',
        borderRadius: 999,
        letterSpacing: 0.5,
        textTransform: 'uppercase',
        fontFamily: 'ui-monospace, monospace',
        flexShrink: 0,
        lineHeight: 1,
        border: `1px solid ${fg}33`,
      }}
    >
      {vt}
    </span>
  );
}

// ── Handle style ───────────────────────────────────────────────────────────────

function mkHandle(port: SerializedPort): React.CSSProperties {
  const ctrl = port.function === 'CONTROL';
  const col = ctrl ? CTRL_COL : NET_COL;
  return {
    width: 12,
    height: 12,
    background: col,
    border: `2px solid rgba(2, 6, 23, 0.9)`,
    borderRadius: ctrl ? 2 : '50%',
    transform: ctrl ? 'rotate(45deg)' : undefined,
  };
}

// ── Port rows ─────────────────────────────────────────────────────────────────

function InputRow({ port, expanded }: { port: SerializedPort; expanded: boolean }) {
  const [hov, setHov] = useState(false);
  const hasValue = port.value !== null && port.value !== undefined;
  return (
    <div
      style={{ background: hov ? CV.portHov : 'transparent', transition: 'background 0.1s', position: 'relative', borderRadius: 10 }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', minHeight: 34 }}>
        <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={mkHandle(port)} />
        <span style={{ color: ACCENT, fontSize: 9, fontWeight: 700, textTransform: 'uppercase' }}>in</span>
        <span style={{ fontSize: 12, color: CV.text, flex: 1, fontFamily: 'ui-sans-serif, sans-serif' }}>
          {port.name}
        </span>
        {(expanded || hov) && <ValueChip vt={port.valueType} />}
      </div>
      {expanded && hasValue && (
        <div style={{ padding: '0 10px 8px 34px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={ACCENT} />
        </div>
      )}
    </div>
  );
}

function OutputRow({ port, expanded }: { port: SerializedPort; expanded: boolean }) {
  const [hov, setHov] = useState(false);
  const hasValue = port.value !== null && port.value !== undefined;
  return (
    <div
      style={{ background: hov ? CV.portHov : 'transparent', transition: 'background 0.1s', position: 'relative', borderRadius: 10 }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', justifyContent: 'flex-end', minHeight: 34 }}>
        {(expanded || hov) && <ValueChip vt={port.valueType} />}
        <span style={{ color: ACCENT, fontSize: 9, fontWeight: 700, textTransform: 'uppercase' }}>out</span>
        <span style={{ fontSize: 12, color: CV.text, fontFamily: 'ui-sans-serif, sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {port.name}
        </span>
        <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={mkHandle(port)} />
      </div>
      {expanded && hasValue && (
        <div style={{ padding: '0 34px 8px 10px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={ACCENT} />
        </div>
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function NetworkNode({ id: _id, data, selected }: NodeProps<Node<NodeData>>) {
  const enterSubnetwork = usePaneStore((s) => s.enterSubnetwork);
  const renameNode = usePaneStore((s) => s.renameNode);
  const [enterHov, setEnterHov] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandHov, setExpandHov] = useState(false);
  const [cardHovered, setCardHovered] = useState(false);

  const traceInfo = useTraceStore((s) => s.nodeStates[_id]);

  const onEnter = useCallback(() => {
    if (data.subnetworkId) enterSubnetwork(data.subnetworkId as string, data.label as string);
  }, [data.subnetworkId, data.label, enterSubnetwork]);

  const inputs = (data.inputs ?? []) as SerializedPort[];
  const outputs = (data.outputs ?? []) as SerializedPort[];
  const hasPorts = inputs.length > 0 || outputs.length > 0;
  const isRunning = traceInfo?.state === 'running';
  const hasError = traceInfo?.state === 'error';
  const visualState = getNodeVisualState(traceInfo, selected);
  const actionsVisible = cardHovered || selected || expanded || isRunning || hasError;

  return (
    <div
      className={nodeCardClassName(visualState)}
      onMouseEnter={() => setCardHovered(true)}
      onMouseLeave={() => {
        setCardHovered(false);
        setEnterHov(false);
        setExpandHov(false);
      }}
      style={{
        ...nodeCardStyle(NET_COL),
        minWidth: 220,
        display: 'flex',
      }}
    >
      <div className="node-accent-rail" style={nodeAccentRailStyle(NET_COL, visualState)} />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {/* Header */}
        <div
          className="node-header"
          style={{
            padding: '11px 12px 10px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {/* Subgraph icon — rounded square */}
          <div
            style={{
              width: 16, height: 16, borderRadius: 4,
              border: `1.5px solid ${ACCENT}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <div style={{ width: 6, height: 6, borderRadius: 2, background: ACCENT }} />
          </div>

          <EditableNodeTitle
            label={data.label as string}
            accent={ACCENT}
            onRename={(name) => renameNode(_id, name)}
          />

          {/* Trace status badge */}
          {traceInfo && traceInfo.state === 'done' && traceInfo.durationMs !== undefined && (
            <StatusBadge state="done" label={`${Math.round(traceInfo.durationMs)}ms`} />
          )}
          {traceInfo && traceInfo.state === 'running' && (
            <StatusBadge state="running" label="running" />
          )}
          {traceInfo && traceInfo.state === 'paused' && (
            <StatusBadge state="paused" label="paused" />
          )}
          {traceInfo && traceInfo.state === 'error' && (
            <StatusBadge state="error" label="error" title={traceInfo.error} />
          )}

          {/* Badges */}
          <span
            style={{
              fontSize: 9, fontWeight: 700, color: ACCENT,
              border: `1px solid ${ACCENT}55`, borderRadius: 4,
              padding: '2px 5px', fontFamily: 'ui-monospace, monospace',
              letterSpacing: 0.4, textTransform: 'uppercase', flexShrink: 0,
            }}
          >
            net
          </span>

          {/* Expand toggle */}
          <button
            onClick={() => setExpanded((e) => !e)}
            onMouseEnter={() => setExpandHov(true)}
            onMouseLeave={() => setExpandHov(false)}
            title={expanded ? 'Collapse values' : 'Expand to show values'}
            style={{
              ...headerActionStyle(actionsVisible, NET_COL, expandHov || expanded),
              color: expandHov || expanded ? NET_COL : 'var(--muted-foreground)',
            }}
          >
            {expanded ? 'Hide' : 'Show'}
          </button>

          {data.subnetworkId && (
            <button
              onClick={onEnter}
              onMouseEnter={() => setEnterHov(true)}
              onMouseLeave={() => setEnterHov(false)}
              style={{
                ...headerActionStyle(actionsVisible, ACCENT, enterHov),
                fontWeight: 700,
              }}
              title="Enter subgraph"
            >
              Enter
            </button>
          )}
        </div>

        {/* Ports */}
        {hasPorts && (
          <div style={{ padding: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div style={{ display: 'grid', gap: 6, minWidth: 0 }}>
              <PortColumnHeader label="inputs" count={inputs.length} />
              {inputs.map((p) => <InputRow key={p.name} port={p} expanded={expanded} />)}
            </div>
            <div style={{ display: 'grid', gap: 6, minWidth: 0 }}>
              <PortColumnHeader label="outputs" count={outputs.length} align="right" />
              {outputs.map((p) => <OutputRow key={p.name} port={p} expanded={expanded} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
