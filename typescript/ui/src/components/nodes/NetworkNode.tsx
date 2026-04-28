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
  CopyPortValueButton,
  StatusBadge,
  PortColumnHeader,
  getNodeVisualState,
  getPortTypeColor,
  getPortValueTypeColors,
  headerActionStyle,
  isMutedLinkedInput,
  nodeAccentRailStyle,
  nodeCardClassName,
  nodeCardStyle,
  PortHoverBadge,
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

function ValueChip({ vt }: { vt: string }) {
  const [bg, fg] = getPortValueTypeColors(vt, NET_COL);
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

function mkHandle(port: SerializedPort, side: 'left' | 'right'): React.CSSProperties {
  const ctrl = port.function === 'CONTROL';
  const mutedLinkedInput = isMutedLinkedInput(port);
  const col = mutedLinkedInput ? CV.muted : getPortTypeColor(port, NET_COL, CTRL_COL);
  return {
    width: 12,
    height: 12,
    top: '50%',
    background: col,
    border: mutedLinkedInput ? `2px solid ${CV.border}` : `2px solid rgba(2, 6, 23, 0.9)`,
    borderRadius: ctrl ? 2 : '50%',
    opacity: mutedLinkedInput ? 0.42 : 1,
    transform: ctrl ? `translate(${side === 'left' ? '-50%' : '50%'}, -50%) rotate(45deg)` : undefined,
  };
}

// ── Port rows ─────────────────────────────────────────────────────────────────

function InputRow({ port, expanded }: { port: SerializedPort; expanded: boolean }) {
  const [hov, setHov] = useState(false);
  const hasValue = port.value !== null && port.value !== undefined;
  const portColor = getPortTypeColor(port, NET_COL, CTRL_COL);
  const mutedLinkedInput = isMutedLinkedInput(port);
  return (
    <div
      style={{ background: !expanded || hov ? CV.portHov : 'transparent', transition: 'background 0.1s', position: 'relative', borderRadius: 10, height: '100%' }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', minHeight: 34 }}>
        <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={mkHandle(port, 'left')} />
        {!expanded && hov && <PortHoverBadge port={port} fallbackColor={NET_COL} />}
        {expanded && hov && hasValue && <CopyPortValueButton value={port.value} />}
        <span style={{ color: mutedLinkedInput ? CV.muted : portColor, fontSize: 9, fontWeight: 700, opacity: mutedLinkedInput ? 0.5 : 1, textTransform: 'uppercase' }}>in</span>
        <span style={{ fontSize: 12, color: mutedLinkedInput ? CV.muted : CV.text, flex: 1, fontFamily: 'ui-sans-serif, sans-serif', opacity: mutedLinkedInput ? 0.56 : 1 }}>
          {port.name}
        </span>
        {expanded && <ValueChip vt={port.valueType} />}
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
  const portColor = getPortTypeColor(port, NET_COL, CTRL_COL);
  return (
    <div
      style={{ background: !expanded || hov ? CV.portHov : 'transparent', transition: 'background 0.1s', position: 'relative', borderRadius: 10, height: '100%' }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', justifyContent: 'flex-end', minHeight: 34 }}>
        {expanded && <ValueChip vt={port.valueType} />}
        {!expanded && hov && <PortHoverBadge port={port} align="left" fallbackColor={NET_COL} />}
        {expanded && hov && hasValue && <CopyPortValueButton value={port.value} align="left" />}
        <span style={{ color: portColor, fontSize: 9, fontWeight: 700, textTransform: 'uppercase' }}>out</span>
        <span style={{ fontSize: 12, color: CV.text, fontFamily: 'ui-sans-serif, sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {port.name}
        </span>
        <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={mkHandle(port, 'right')} />
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
  const portRowCount = Math.max(inputs.length, outputs.length);
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
        minWidth: expanded ? 275 : 344,
        display: 'flex',
      }}
    >
      <div className="node-accent-rail" style={nodeAccentRailStyle(NET_COL, visualState)} />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {/* Header */}
        <div
          className="node-header"
          style={{
            padding: '12px 13px 11px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {/* Subgraph icon — rounded square */}
          <div
            style={{
              width: 18, height: 18, borderRadius: 4,
              border: `1.5px solid ${ACCENT}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <div style={{ width: 7, height: 7, borderRadius: 2, background: ACCENT }} />
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
          <div style={{ padding: 10, display: 'grid', gridTemplateColumns: '3fr 2fr', alignItems: 'start', columnGap: 8, rowGap: 6 }}>
            <div style={{ minWidth: 0 }}>
              <PortColumnHeader label="inputs" count={inputs.length} />
            </div>
            <div style={{ minWidth: 0 }}>
              <PortColumnHeader label="outputs" count={outputs.length} align="right" />
            </div>
            {Array.from({ length: portRowCount }, (_, index) => {
              const input = inputs[index];
              const output = outputs[index];
              return (
                <React.Fragment key={`${input?.name ?? 'empty'}-${output?.name ?? 'empty'}-${index}`}>
                  <div style={{ minWidth: 0, height: '100%' }}>
                    {input ? <InputRow port={input} expanded={expanded} /> : <div style={{ minHeight: 34 }} />}
                  </div>
                  <div style={{ minWidth: 0, height: '100%' }}>
                    {output ? <OutputRow port={output} expanded={expanded} /> : <div style={{ minHeight: 34 }} />}
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
