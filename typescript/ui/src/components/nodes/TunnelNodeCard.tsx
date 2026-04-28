import React, { useEffect, useRef, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeData, SerializedPort } from '../../types/uiTypes';
import { PortValueRenderer } from './PortValueRenderer';
import { graphClient } from '../../api/graphClient';
import { useTraceStore } from '../../store/traceStore';
import {
  CopyPortValueButton,
  StatusBadge,
  PortColumnHeader,
  getNodeVisualState,
  getPortTypeColor,
  headerActionStyle,
  isMutedLinkedInput,
  nodeAccentRailStyle,
  nodeCardClassName,
  nodeCardStyle,
  PortHoverBadge,
} from './nodeVisuals';

const T = {
  bg: 'var(--card)',
  header: 'var(--sidebar)',
  border: 'var(--border)',
  text: 'var(--foreground)',
  muted: 'var(--muted-foreground)',
  input: '#22d3ee',
  output: '#f59e0b',
  control: '#f472b6',
  hover: 'rgba(148, 163, 184, 0.10)',
  surface: 'rgba(15, 23, 42, 0.45)',
};

const FALLBACK_VALUE_TYPES = [
  'ANY',
  'INT',
  'FLOAT',
  'STRING',
  'BOOL',
  'DICT',
  'ARRAY',
  'OBJECT',
  'VECTOR',
  'MATRIX',
  'COLOR',
  'BINARY',
  'IMAGE',
  'LATENT',
  'CONDITIONING',
  'MODEL',
  'CLIP',
  'VAE',
  'MASK',
];

let cachedValueTypes: string[] | null = null;

function handleStyle(port: SerializedPort, accent: string, side: 'left' | 'right'): React.CSSProperties {
  const mutedLinkedInput = isMutedLinkedInput(port);
  const color = mutedLinkedInput ? T.muted : getPortTypeColor(port, accent, T.control);
  const isControl = port.function === 'CONTROL';
  return {
    width: 12,
    height: 12,
    top: '50%',
    background: color,
    border: mutedLinkedInput ? `2px solid ${T.border}` : '2px solid rgba(2, 6, 23, 0.9)',
    borderRadius: port.function === 'CONTROL' ? 2 : '50%',
    opacity: mutedLinkedInput ? 0.42 : 1,
    transform: isControl ? `translate(${side === 'left' ? '-50%' : '50%'}, -50%) rotate(45deg)` : undefined,
  };
}

function RemoveButton({ onClick, visible }: { onClick: () => void; visible: boolean }) {
  return (
    <button
      className="nodrag nopan"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      title="Remove port"
      style={{
        background: 'var(--background)',
        border: 'none',
        color: '#ef4444',
        cursor: 'pointer',
        fontSize: 10,
        width: 18,
        height: 18,
        opacity: visible ? 1 : 0,
        padding: 0,
      }}
    >
      x
    </button>
  );
}

function TunnelPortRow({
  port,
  mode,
  expanded,
  onRemove,
  onRename,
  siblingNames,
}: {
  port: SerializedPort;
  mode: 'input' | 'output';
  expanded: boolean;
  onRemove?: () => void;
  onRename?: (newName: string) => void;
  siblingNames: string[];
}) {
  const [hovered, setHovered] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(port.name);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const isInput = mode === 'input';
  const accent = isInput ? T.input : T.output;
  const portColor = getPortTypeColor(port, accent, T.control);
  const mutedLinkedInput = isMutedLinkedInput(port);

  const beginEdit = () => {
    setEditValue(port.name);
    setError('');
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const commitEdit = () => {
    const trimmed = editValue.trim();
    if (!trimmed) {
      setError('Name required');
      return;
    }
    if (trimmed === port.name) {
      setEditing(false);
      return;
    }
    if (siblingNames.includes(trimmed)) {
      setError('Name exists');
      return;
    }
    setEditing(false);
    onRename?.(trimmed);
  };

  const name = editing ? (
    <input
      ref={inputRef}
      className="nodrag nopan"
      value={editValue}
      onChange={(event) => {
        setEditValue(event.target.value);
        setError('');
      }}
      onBlur={commitEdit}
      onMouseDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        event.stopPropagation();
        if (event.key === 'Enter') commitEdit();
        if (event.key === 'Escape') setEditing(false);
      }}
      style={{
        flex: 1,
        minWidth: 0,
        background: 'transparent',
        border: `1px solid ${error ? '#ef4444' : accent}`,
        borderRadius: 5,
        color: T.text,
        fontFamily: 'ui-sans-serif, sans-serif',
        fontSize: 12,
        padding: '2px 5px',
        outline: 'none',
      }}
    />
  ) : (
    <span
      title={onRename ? 'Double-click to rename' : undefined}
      onDoubleClick={onRename ? beginEdit : undefined}
      style={{
        flex: 1,
        minWidth: 0,
        color: mutedLinkedInput ? T.muted : T.text,
        cursor: onRename ? 'text' : 'default',
        fontSize: 12,
        opacity: mutedLinkedInput ? 0.56 : 1,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {port.name}
    </span>
  );

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ position: 'relative', borderRadius: 10, background: !expanded || hovered ? T.hover : 'transparent' }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          minHeight: 34,
          padding: isInput ? '7px 18px 7px 10px' : '7px 10px 7px 18px',
        }}
      >
        {isInput ? (
          <>
            {onRemove && <RemoveButton onClick={onRemove} visible={hovered && !editing} />}
            {!expanded && hovered && <PortHoverBadge port={port} align="left" fallbackColor={accent} />}
            {expanded && hovered && port.value != null && <CopyPortValueButton value={port.value} align="left" />}
            <span style={{ color: mutedLinkedInput ? T.muted : portColor, fontSize: 9, fontWeight: 700, opacity: mutedLinkedInput ? 0.5 : 1, textTransform: 'uppercase' }}>in</span>
            {name}
            <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={handleStyle(port, accent, 'right')} />
          </>
        ) : (
          <>
            <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={handleStyle(port, accent, 'left')} />
            {!expanded && hovered && <PortHoverBadge port={port} fallbackColor={accent} />}
            {expanded && hovered && port.value != null && <CopyPortValueButton value={port.value} />}
            <span style={{ color: mutedLinkedInput ? T.muted : portColor, fontSize: 9, fontWeight: 700, opacity: mutedLinkedInput ? 0.5 : 1, textTransform: 'uppercase' }}>out</span>
            {name}
            {onRemove && <RemoveButton onClick={onRemove} visible={hovered && !editing} />}
          </>
        )}
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 10, padding: '0 10px 6px' }}>{error}</div>}
      {expanded && port.value != null && (
        <div style={{ padding: isInput ? '0 18px 8px 34px' : '0 10px 8px 34px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={accent} />
        </div>
      )}
    </div>
  );
}

function PortEditor({
  direction,
  onAdd,
}: {
  direction: 'input' | 'output';
  onAdd: (name: string, direction: 'input' | 'output', portFunction: 'DATA' | 'CONTROL', valueType: string) => void;
}) {
  const [name, setName] = useState('');
  const [portFunction, setPortFunction] = useState<'DATA' | 'CONTROL'>('DATA');
  const [valueType, setValueType] = useState('ANY');
  const [valueTypes, setValueTypes] = useState(cachedValueTypes ?? FALLBACK_VALUE_TYPES);
  const accent = direction === 'input' ? T.input : T.output;

  useEffect(() => {
    if (cachedValueTypes) return;
    graphClient.getPortTypes()
      .then((types) => {
        if (types.length === 0) return;
        cachedValueTypes = types;
        setValueTypes(types);
      })
      .catch(() => {});
  }, []);

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd(trimmed, direction, portFunction, portFunction === 'CONTROL' ? 'ANY' : valueType);
    setName('');
  };

  return (
    <div className="nodrag nopan" style={{ borderTop: `1px solid ${T.border}`, padding: 10 }}>
      <div
        data-tunnel-add-zone={direction}
        style={{
          border: `1px dashed ${accent}88`,
          borderRadius: 10,
          color: accent,
          background: `${accent}14`,
          fontSize: 10,
          fontWeight: 700,
          marginBottom: 8,
          padding: '8px 10px',
          textTransform: 'uppercase',
        }}
      >
        {direction === 'input' ? 'Drop node input here' : 'Drop node output here'}
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <select
          className="nodrag nopan"
          value={portFunction}
          onChange={(event) => setPortFunction(event.target.value as 'DATA' | 'CONTROL')}
          onMouseDown={(event) => event.stopPropagation()}
          style={{ flex: 1, background: 'var(--background)', color: T.text, border: `1px solid ${T.border}`, borderRadius: 5, fontFamily: 'ui-sans-serif, sans-serif', padding: 4 }}
        >
          <option value="DATA" style={{ background: '#020617', color: '#e2e8f0' }}>data</option>
          <option value="CONTROL" style={{ background: '#020617', color: '#e2e8f0' }}>control</option>
        </select>
        <select
          className="nodrag nopan"
          value={portFunction === 'CONTROL' ? 'ANY' : valueType}
          disabled={portFunction === 'CONTROL'}
          onChange={(event) => setValueType(event.target.value)}
          onMouseDown={(event) => event.stopPropagation()}
          style={{ flex: 1, background: 'var(--background)', color: T.text, border: `1px solid ${T.border}`, borderRadius: 5, fontFamily: 'ui-sans-serif, sans-serif', padding: 4 }}
        >
          {valueTypes.map((type) => (
            <option key={type} value={type} style={{ background: '#020617', color: '#e2e8f0' }}>
              {type.toLowerCase()}
            </option>
          ))}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          className="nodrag nopan"
          value={name}
          onChange={(event) => setName(event.target.value)}
          onMouseDown={(event) => event.stopPropagation()}
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === 'Enter') submit();
          }}
          placeholder="port name..."
          style={{ flex: 1, minWidth: 0, background: 'var(--background)', color: T.text, border: `1px solid ${T.border}`, borderRadius: 5, fontFamily: 'ui-sans-serif, sans-serif', padding: '4px 7px' }}
        />
        <button
          className="nodrag nopan"
          onClick={submit}
          onMouseDown={(event) => event.stopPropagation()}
          style={{ background: `${accent}22`, border: `1px solid ${accent}88`, borderRadius: 5, color: accent, cursor: 'pointer', width: 26 }}
          title="Add port"
        >
          +
        </button>
      </div>
    </div>
  );
}

type TunnelNodeCardProps = {
  id: string;
  data: NodeData;
  selected: boolean;
  mode: 'input' | 'output';
};

function TunnelNodeCardComponent({ id, data, selected, mode }: TunnelNodeCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cardHovered, setCardHovered] = useState(false);
  const ports = (mode === 'input' ? data.outputs : data.inputs) as SerializedPort[];
  const accent = mode === 'input' ? T.input : T.output;
  const onAdd = data.onAddTunnelPort;
  const onRemove = data.onRemoveTunnelPort;
  const onRename = data.onRenameTunnelPort;
  const traceInfo = useTraceStore((s) => s.nodeStates[id]);
  const isRunning = traceInfo?.state === 'running';
  const hasError = traceInfo?.state === 'error';
  const visualState = getNodeVisualState(traceInfo, selected);
  const actionsVisible = cardHovered || selected || expanded || isRunning || hasError;

  const wrap = (fn: () => Promise<void>) => () => {
    if (busy) return;
    setBusy(true);
    fn().finally(() => setBusy(false));
  };

  return (
    <div
      className={nodeCardClassName(visualState)}
      onMouseEnter={() => setCardHovered(true)}
      onMouseLeave={() => setCardHovered(false)}
      style={{
        ...nodeCardStyle(accent),
        minWidth: expanded ? 300 : 375,
        opacity: busy ? 0.7 : 1,
      }}
    >
      <div className="node-accent-rail" style={nodeAccentRailStyle(accent, visualState)} />
      <div className="node-header" style={{ padding: '12px 13px 11px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: accent, fontWeight: 800, fontSize: 13.2 }}>{mode === 'input' ? 'IN' : 'OUT'}</span>
          <span style={{ color: T.text, flex: 1, fontWeight: 700, fontSize: 14.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {mode === 'input' ? 'Tunnel Inputs' : 'Tunnel Outputs'}
          </span>
          {traceInfo?.state === 'running' && <StatusBadge state="running" label="running" />}
          {traceInfo?.state === 'error' && <StatusBadge state="error" label="error" title={traceInfo.error} />}
          <span style={{ color: accent, border: `1px solid ${accent}66`, borderRadius: 999, fontSize: 9, padding: '2px 7px' }}>
            {ports.length}
          </span>
          <button
            onClick={() => setExpanded((value) => !value)}
            style={headerActionStyle(actionsVisible, accent, expanded)}
          >
            {expanded ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>
      <div style={{ padding: 10, display: 'grid', gap: 6 }}>
        <PortColumnHeader label={mode === 'input' ? 'inputs' : 'outputs'} count={ports.length} />
        {ports.map((port) => (
          <TunnelPortRow
            key={port.name}
            port={port}
            mode={mode}
            expanded={expanded}
            onRemove={onRemove ? wrap(() => onRemove(port.name, mode)) : undefined}
            onRename={onRename ? (newName) => wrap(() => onRename(port.name, newName, mode))() : undefined}
            siblingNames={ports.map((p) => p.name).filter((name) => name !== port.name)}
          />
        ))}
        {ports.length === 0 && (
          <div style={{ color: T.muted, border: `1px dashed ${T.border}`, borderRadius: 10, padding: 12, textAlign: 'center', fontSize: 11 }}>
            {mode === 'input' ? 'No tunnel inputs yet' : 'No tunnel outputs yet'}
          </div>
        )}
      </div>
      {onAdd && (
        <PortEditor
          direction={mode}
          onAdd={(name, direction, portFunction, valueType) => {
            onAdd(name, direction, portFunction, valueType).catch(console.error);
          }}
        />
      )}
    </div>
  );
}

export const TunnelNodeCard = React.memo(
  TunnelNodeCardComponent,
  (prev, next) =>
    prev.id === next.id &&
    prev.mode === next.mode &&
    prev.selected === next.selected &&
    prev.data === next.data,
);
TunnelNodeCard.displayName = 'TunnelNodeCard';
