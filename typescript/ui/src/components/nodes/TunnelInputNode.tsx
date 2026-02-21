/**
 * TunnelInputNode — the subnetwork's own tunnel port proxy, shown INSIDE the
 * subnet view.
 *
 * Renders:
 *   - Tunnel INPUT ports  (network.inputs)  => right-side source handles (data IN)
 *   - Tunnel OUTPUT ports (network.outputs) => left-side target handles  (data OUT)
 *   - A port-editor row at the bottom to add/remove ports live.
 */
import React, { useState, useRef } from 'react';
import { Handle, Position, NodeProps, Node } from '@xyflow/react';
import type { NodeData, SerializedPort } from '../../types/uiTypes';
import { PortValueRenderer } from './PortValueRenderer';

// -- Design tokens ------------------------------------------------------------

const T = {
  bg:        '#141209',
  header:    '#0d0a04',
  border:    '#4a6040',
  borderSel: '#7fa668',
  accent:    '#7fa668',
  accentOut: '#bf7a2a',
  shadow:    '0 4px 20px rgba(0,0,0,0.8), 0 1px 4px rgba(0,0,0,0.6)',
  shadowSel: '0 0 0 2px #7fa668, 0 6px 24px rgba(127,166,104,0.35)',
  text:      '#e8d5a8',
  muted:     '#7a8c5a',
  portHov:   '#1a1e10',
  divider:   '#2a3520',
  inputBg:   '#0d0a04',
};

// -- Handle styles ------------------------------------------------------------

function mkSrc(port: SerializedPort): React.CSSProperties {
  const c = port.function === 'CONTROL' ? '#f87171' : T.accent;
  return {
    width: 12, height: 12, background: c,
    border: `2.5px solid ${T.header}`,
    borderRadius: port.function === 'CONTROL' ? 2 : '50%',
    boxShadow: `0 0 8px ${c}99`,
  };
}
function mkTgt(port: SerializedPort): React.CSSProperties {
  const c = port.function === 'CONTROL' ? '#f87171' : T.accentOut;
  return {
    width: 12, height: 12, background: c,
    border: `2.5px solid ${T.header}`,
    borderRadius: port.function === 'CONTROL' ? 2 : '50%',
    boxShadow: `0 0 8px ${c}99`,
  };
}

// -- Small remove button ------------------------------------------------------

function RemoveBtn({ onClick, visible }: { onClick: () => void; visible: boolean }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title="Remove port"
      style={{
        background: 'transparent', border: 'none', color: '#ef4444',
        cursor: 'pointer', fontSize: 10, width: 16, height: 16,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 3, padding: 0, flexShrink: 0,
        opacity: visible ? 1 : 0, transition: 'opacity 0.1s',
      }}
    >
      {'✕'}
    </button>
  );
}

// -- Source port row (tunnel INPUT => right-side source) ----------------------

function SourcePortRow({
  port, expanded, onRemove,
}: {
  port: SerializedPort; expanded: boolean; onRemove?: () => void;
}) {
  const [hov, setHov] = useState(false);
  return (
    <div
      style={{ background: hov ? T.portHov : 'transparent', transition: 'background 0.1s', position: 'relative' }}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 18px 5px 10px', minHeight: 30 }}>
        {onRemove && <RemoveBtn onClick={onRemove} visible={hov} />}
        <span style={{ fontSize: 9, fontFamily: 'ui-monospace,monospace', color: T.accent, textTransform: 'uppercase', letterSpacing: 0.4, flexShrink: 0 }}>in</span>
        <span style={{ fontSize: 12, color: T.text, flex: 1, fontFamily: 'ui-sans-serif,sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{port.name}</span>
        <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={mkSrc(port)} />
      </div>
      {expanded && port.value != null && (
        <div style={{ padding: '0 18px 6px 32px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={T.accent} />
        </div>
      )}
    </div>
  );
}

// -- Target port row (tunnel OUTPUT => left-side target) ----------------------

function TargetPortRow({
  port, expanded, onRemove,
}: {
  port: SerializedPort; expanded: boolean; onRemove?: () => void;
}) {
  const [hov, setHov] = useState(false);
  return (
    <div
      style={{ background: hov ? T.portHov : 'transparent', transition: 'background 0.1s', position: 'relative' }}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px 5px 18px', minHeight: 30 }}>
        <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={mkTgt(port)} />
        <span style={{ fontSize: 9, fontFamily: 'ui-monospace,monospace', color: T.accentOut, textTransform: 'uppercase', letterSpacing: 0.4, flexShrink: 0 }}>out</span>
        <span style={{ fontSize: 12, color: T.text, flex: 1, fontFamily: 'ui-sans-serif,sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{port.name}</span>
        {onRemove && <RemoveBtn onClick={onRemove} visible={hov} />}
      </div>
      {expanded && port.value != null && (
        <div style={{ padding: '0 10px 6px 32px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={T.accentOut} />
        </div>
      )}
    </div>
  );
}

// -- Port editor --------------------------------------------------------------

function PortEditor({ onAdd }: { onAdd: (name: string, dir: 'input' | 'output') => void }) {
  const [name, setName] = useState('');
  const [dir, setDir]   = useState<'input' | 'output'>('input');
  const [iHov, setIHov] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  const submit = () => {
    const t = name.trim();
    if (!t) return;
    onAdd(t, dir);
    setName('');
    ref.current?.focus();
  };

  return (
    <div style={{ borderTop: `1px solid ${T.divider}`, padding: '8px 10px', background: T.inputBg }}>
      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
        <div style={{ display: 'flex', borderRadius: 5, overflow: 'hidden', border: `1px solid ${T.border}`, flexShrink: 0 }}>
          {(['input', 'output'] as const).map((d) => (
            <button key={d} onClick={() => setDir(d)}
              style={{
                background: dir === d ? (d === 'input' ? `${T.accent}22` : `${T.accentOut}22`) : 'transparent',
                border: 'none',
                borderRight: d === 'input' ? `1px solid ${T.border}` : 'none',
                color: dir === d ? (d === 'input' ? T.accent : T.accentOut) : T.muted,
                cursor: 'pointer', fontSize: 9, fontFamily: 'ui-monospace,monospace',
                fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5,
                padding: '3px 7px', transition: 'background 0.1s, color 0.1s',
              }}>
              {d === 'input' ? '\u2192 in' : '\u2190 out'}
            </button>
          ))}
        </div>
        <input
          ref={ref} value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          onMouseEnter={() => setIHov(true)} onMouseLeave={() => setIHov(false)}
          placeholder={'port name…'}
          style={{
            flex: 1, background: 'transparent',
            border: `1px solid ${iHov ? T.accent : T.border}`,
            borderRadius: 5, color: T.text, fontSize: 11,
            fontFamily: 'ui-monospace,monospace', outline: 'none',
            padding: '4px 7px', transition: 'border-color 0.1s', minWidth: 0,
          }}
        />
        <button onClick={submit} title="Add port"
          style={{ background: `${T.accent}22`, border: `1px solid ${T.accent}55`, borderRadius: 5, color: T.accent, cursor: 'pointer', fontSize: 14, width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, padding: 0 }}
          onMouseEnter={(e) => (e.currentTarget.style.background = `${T.accent}40`)}
          onMouseLeave={(e) => (e.currentTarget.style.background = `${T.accent}22`)}>
          +
        </button>
      </div>
    </div>
  );
}

// -- Main component -----------------------------------------------------------

export function TunnelInputNode({ data, selected }: NodeProps<Node<NodeData>>) {
  const [expanded, setExpanded] = useState(false);
  const [exHov,    setExHov]    = useState(false);
  const [busy,     setBusy]     = useState(false);

  // Tunnel INPUT ports  => right-side source handles (data enters subnet)
  const sourceports = (data.outputs ?? []) as SerializedPort[];
  // Tunnel OUTPUT ports => left-side target handles  (data exits subnet)
  const targetports = (data.inputs  ?? []) as SerializedPort[];

  const onAdd    = data.onAddTunnelPort    as ((n: string, d: 'input' | 'output') => Promise<void>) | undefined;
  const onRemove = data.onRemoveTunnelPort as ((n: string, d: 'input' | 'output') => Promise<void>) | undefined;

  const wrap = (fn: () => Promise<void>) => () => {
    if (busy) return;
    setBusy(true);
    fn().finally(() => setBusy(false));
  };

  return (
    <div style={{
      background: T.bg,
      border: `1.5px solid ${selected ? T.borderSel : T.border}`,
      borderRadius: 10, minWidth: 200, overflow: 'hidden',
      boxShadow: selected ? T.shadowSel : T.shadow,
      transition: 'box-shadow 0.15s, border-color 0.15s',
      display: 'flex', opacity: busy ? 0.7 : 1,
    }}>
      {/* Left accent bar */}
      <div style={{ width: 4, background: T.accent, flexShrink: 0, borderRadius: '10px 0 0 10px' }} />

      <div style={{ flex: 1, overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ background: T.header, padding: '8px 10px', display: 'flex', alignItems: 'center', gap: 7, borderBottom: `1px solid ${T.border}` }}>
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" style={{ flexShrink: 0 }}>
            <path d="M1 6.5h8M6 3l3.5 3.5L6 10" stroke={T.accent} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="11.5" cy="6.5" r="1.2" fill={T.accent} />
          </svg>
          <span style={{ fontWeight: 700, fontSize: 12, color: T.text, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'ui-sans-serif,sans-serif' }}>
            {data.label}
          </span>
          {sourceports.length > 0 && (
            <span style={{ fontSize: 9, fontWeight: 700, color: T.accent, border: `1px solid ${T.accent}55`, borderRadius: 4, padding: '2px 5px', fontFamily: 'ui-monospace,monospace', letterSpacing: 0.4, textTransform: 'uppercase', flexShrink: 0 }}>
              {sourceports.length} in
            </span>
          )}
          {targetports.length > 0 && (
            <span style={{ fontSize: 9, fontWeight: 700, color: T.accentOut, border: `1px solid ${T.accentOut}55`, borderRadius: 4, padding: '2px 5px', fontFamily: 'ui-monospace,monospace', letterSpacing: 0.4, textTransform: 'uppercase', flexShrink: 0 }}>
              {targetports.length} out
            </span>
          )}
          <button
            onClick={() => setExpanded((e) => !e)}
            onMouseEnter={() => setExHov(true)} onMouseLeave={() => setExHov(false)}
            title={expanded ? 'Collapse values' : 'Expand to show values'}
            style={{ background: exHov ? '#1a1e10' : 'transparent', border: `1px solid ${T.border}`, borderRadius: 6, color: exHov ? T.text : T.muted, cursor: 'pointer', fontSize: 10, width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'ui-monospace,monospace', flexShrink: 0, transition: 'background 0.1s, color 0.1s', padding: 0 }}>
            {expanded ? '\u25b2' : '\u25bc'}
          </button>
        </div>

        {/* Tunnel OUTPUT ports => left-side target handles */}
        {targetports.map((p) => (
          <TargetPortRow key={p.name} port={p} expanded={expanded}
            onRemove={onRemove ? wrap(() => onRemove(p.name, 'output')) : undefined} />
        ))}

        {/* Divider when both types are present */}
        {targetports.length > 0 && sourceports.length > 0 && (
          <div style={{ height: 1, background: T.divider, margin: '0 10px' }} />
        )}

        {/* Tunnel INPUT ports => right-side source handles */}
        {sourceports.map((p) => (
          <SourcePortRow key={p.name} port={p} expanded={expanded}
            onRemove={onRemove ? wrap(() => onRemove(p.name, 'input')) : undefined} />
        ))}

        {/* Empty state */}
        {sourceports.length === 0 && targetports.length === 0 && (
          <div style={{ padding: '10px 14px', fontFamily: 'ui-monospace,monospace', fontSize: 10, color: T.muted }}>
            no tunnel ports — add one below
          </div>
        )}

        {/* Port editor (only when callbacks are wired) */}
        {onAdd && <PortEditor onAdd={(n, d) => { onAdd(n, d).catch(console.error); }} />}
      </div>
    </div>
  );
}
