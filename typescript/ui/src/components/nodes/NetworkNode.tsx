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

// ── Trace glow colours ────────────────────────────────────────────────────────

const TRACE_GLOW: Record<string, string> = {
  pending: '#818cf8',
  running: '#facc15',
  paused:  '#f97316',
  done:    '#4ade80',
  error:   '#f87171',
};

// ── Design tokens ─────────────────────────────────────────────────────────────

const T = {
  bg:         '#1a1626',
  header:     '#120e1f',
  border:     '#3b2f5e',
  borderSel:  '#a78bfa',
  accent:     '#a78bfa',
  shadow:     '0 4px 20px rgba(0,0,0,0.6), 0 1px 4px rgba(0,0,0,0.4)',
  shadowSel:  '0 0 0 2px #a78bfa, 0 6px 24px rgba(167,139,250,0.4)',
  text:       '#e2e8f0',
  muted:      '#7c6fa0',
  portHov:    '#1e1830',
  handleData: '#a78bfa',
  handleCtrl: '#f87171',
};

// ── Value-type chip (same palette as FunctionNode) ─────────────────────────────

const CHIP_COLORS: Record<string, [string, string]> = {
  int:    ['#172554', '#60a5fa'],
  float:  ['#172554', '#60a5fa'],
  number: ['#172554', '#60a5fa'],
  str:    ['#052e16', '#34d399'],
  string: ['#052e16', '#34d399'],
  bool:   ['#422006', '#fbbf24'],
  any:    ['#1f1833', '#7c6fa0'],
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
        padding: '2px 5px',
        borderRadius: 4,
        letterSpacing: 0.4,
        textTransform: 'uppercase',
        fontFamily: 'ui-monospace, monospace',
        flexShrink: 0,
        lineHeight: 1,
      }}
    >
      {vt}
    </span>
  );
}

// ── Handle style ───────────────────────────────────────────────────────────────

function mkHandle(port: SerializedPort): React.CSSProperties {
  const ctrl = port.function === 'CONTROL';
  const col = ctrl ? T.handleCtrl : T.handleData;
  return {
    width: 12,
    height: 12,
    background: col,
    border: `2.5px solid ${T.header}`,
    borderRadius: ctrl ? 2 : '50%',
    transform: ctrl ? 'rotate(45deg)' : undefined,
    boxShadow: `0 0 8px ${col}99`,
  };
}

// ── Port rows ─────────────────────────────────────────────────────────────────

function InputRow({ port, expanded }: { port: SerializedPort; expanded: boolean }) {
  const [hov, setHov] = useState(false);
  const hasValue = port.value !== null && port.value !== undefined;
  return (
    <div
      style={{
        background: hov ? T.portHov : 'transparent',
        transition: 'background 0.1s',
        position: 'relative',
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 12px 5px 18px',
          minHeight: 30,
        }}
      >
        <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={mkHandle(port)} />
        <span style={{ fontSize: 12, color: T.text, flex: 1, fontFamily: 'ui-sans-serif, sans-serif' }}>
          {port.name}
        </span>
        <ValueChip vt={port.valueType} />
      </div>
      {expanded && hasValue && (
        <div style={{ padding: '0 12px 6px 18px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={T.accent} />
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
      style={{
        background: hov ? T.portHov : 'transparent',
        transition: 'background 0.1s',
        position: 'relative',
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 18px 5px 12px',
          justifyContent: 'flex-end',
          minHeight: 30,
        }}
      >
        <ValueChip vt={port.valueType} />
        <span style={{ fontSize: 12, color: T.text, fontFamily: 'ui-sans-serif, sans-serif' }}>
          {port.name}
        </span>
        <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={mkHandle(port)} />
      </div>
      {expanded && hasValue && (
        <div style={{ padding: '0 18px 6px 12px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={T.accent} />
        </div>
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function NetworkNode({ id: _id, data, selected }: NodeProps<Node<NodeData>>) {
  const enterSubnetwork = usePaneStore((s) => s.enterSubnetwork);
  const [enterHov, setEnterHov] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandHov, setExpandHov] = useState(false);

  const traceInfo = useTraceStore((s) => s.nodeStates[_id]);
  const glowColor = traceInfo ? TRACE_GLOW[traceInfo.state] : undefined;
  const traceShadow = glowColor
    ? `0 0 0 1.5px ${glowColor}, 0 0 18px ${glowColor}88`
    : undefined;
  const baseShadow = selected ? T.shadowSel : T.shadow;
  const cardShadow = traceShadow ? `${traceShadow}, ${baseShadow}` : baseShadow;

  const onEnter = useCallback(() => {
    if (data.subnetworkId) enterSubnetwork(data.subnetworkId as string, data.label as string);
  }, [data.subnetworkId, data.label, enterSubnetwork]);

  const inputs = (data.inputs ?? []) as SerializedPort[];
  const outputs = (data.outputs ?? []) as SerializedPort[];
  const hasPorts = inputs.length > 0 || outputs.length > 0;

  return (
    <div
      style={{
        background: T.bg,
        border: `1.5px solid ${selected ? T.borderSel : T.border}`,
        borderRadius: 10,
        minWidth: 220,
        overflow: 'hidden',
        boxShadow: cardShadow,
        transition: 'box-shadow 0.15s, border-color 0.15s',
        display: 'flex',
      }}
    >
      {/* Left accent bar */}
      <div style={{ width: 4, background: T.accent, flexShrink: 0, borderRadius: '10px 0 0 10px' }} />

      <div style={{ flex: 1, overflow: 'hidden' }}>
        {/* Header */}
        <div
          style={{
            background: T.header,
            padding: '9px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          {/* Subgraph icon — rounded square */}
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: 4,
              border: `1.5px solid ${T.accent}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: `0 0 6px ${T.accent}66`,
            }}
          >
            <div style={{ width: 6, height: 6, borderRadius: 2, background: T.accent }} />
          </div>

          <span
            style={{
              fontWeight: 700,
              fontSize: 13,
              color: T.text,
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontFamily: 'ui-sans-serif, sans-serif',
            }}
          >
            {data.label}
          </span>

          {/* Trace status badge */}
          {traceInfo && traceInfo.state === 'done' && traceInfo.durationMs !== undefined && (
            <span style={{
              fontSize: 9, fontFamily: 'ui-monospace, monospace', color: TRACE_GLOW.done,
              background: '#052e16', borderRadius: 4, padding: '2px 5px', flexShrink: 0,
            }}>
              ✓ {traceInfo.durationMs}ms
            </span>
          )}
          {traceInfo && traceInfo.state === 'running' && (
            <span style={{
              fontSize: 9, fontFamily: 'ui-monospace, monospace', color: TRACE_GLOW.running,
              background: '#422006', borderRadius: 4, padding: '2px 5px', flexShrink: 0,
            }}>
              ⏳
            </span>
          )}
          {traceInfo && traceInfo.state === 'paused' && (
            <span style={{
              fontSize: 9, fontFamily: 'ui-monospace, monospace', color: TRACE_GLOW.paused,
              background: '#431407', borderRadius: 4, padding: '2px 5px', flexShrink: 0,
            }}>
              ⏸ wait
            </span>
          )}
          {traceInfo && traceInfo.state === 'error' && (
            <span style={{
              fontSize: 9, fontFamily: 'ui-monospace, monospace', color: TRACE_GLOW.error,
              background: '#2d0a0a', borderRadius: 4, padding: '2px 5px', flexShrink: 0,
              maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }} title={traceInfo.error}>
              ✕ err
            </span>
          )}

          {/* Badges */}
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: T.accent,
              border: `1px solid ${T.accent}55`,
              borderRadius: 4,
              padding: '2px 5px',
              fontFamily: 'ui-monospace, monospace',
              letterSpacing: 0.4,
              textTransform: 'uppercase',
              flexShrink: 0,
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
              background: expandHov ? '#1e1830' : 'transparent',
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              color: expandHov ? T.text : T.muted,
              cursor: 'pointer',
              fontSize: 10,
              width: 22,
              height: 22,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'ui-monospace, monospace',
              flexShrink: 0,
              transition: 'background 0.1s, color 0.1s',
              lineHeight: 1,
              padding: 0,
            }}
          >
            {expanded ? '▲' : '▼'}
          </button>

          {data.subnetworkId && (
            <button
              onClick={onEnter}
              onMouseEnter={() => setEnterHov(true)}
              onMouseLeave={() => setEnterHov(false)}
              style={{
                background: enterHov ? T.accent : 'transparent',
                border: `1px solid ${T.accent}`,
                borderRadius: 6,
                color: enterHov ? T.bg : T.accent,
                cursor: 'pointer',
                fontSize: 10,
                padding: '3px 8px',
                fontFamily: 'ui-monospace, monospace',
                flexShrink: 0,
                transition: 'background 0.1s, color 0.1s',
                lineHeight: 1.4,
              }}
              title="Enter subgraph"
            >
              ⤵ Enter
            </button>
          )}
        </div>

        {/* Ports */}
        {hasPorts && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
            <div>{inputs.map((p) => <InputRow key={p.name} port={p} expanded={expanded} />)}</div>
            <div style={{ borderLeft: `1px solid ${T.border}` }}>
              {outputs.map((p) => <OutputRow key={p.name} port={p} expanded={expanded} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
