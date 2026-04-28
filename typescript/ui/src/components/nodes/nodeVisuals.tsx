import React from 'react';
import type { SerializedPort } from '../../types/uiTypes';
import type { NodeTraceInfo, NodeTraceState } from '../../store/traceStore';

export const TRACE_COLORS: Record<Exclude<NodeTraceState, 'idle'>, string> = {
  pending: '#818cf8',
  running: '#facc15',
  paused: '#f97316',
  waiting: '#a78bfa',
  done: '#4ade80',
  error: '#f87171',
};

export type NodeVisualState = 'idle' | 'selected' | 'running' | 'error' | 'paused' | 'waiting' | 'done';

export function getNodeVisualState(traceInfo: NodeTraceInfo | undefined, selected: boolean): NodeVisualState {
  if (traceInfo?.state === 'error') return 'error';
  if (traceInfo?.state === 'running' || traceInfo?.state === 'pending') return 'running';
  if (traceInfo?.state === 'waiting') return 'waiting';
  if (traceInfo?.state === 'paused') return 'paused';
  if (selected) return 'selected';
  if (traceInfo?.state === 'done') return 'done';
  return 'idle';
}

export function nodeCardClassName(state: NodeVisualState): string {
  return `node-card node-card--${state}`;
}

export function nodeCardStyle(accent: string): React.CSSProperties {
  return { '--node-accent': accent } as React.CSSProperties;
}

export function nodeAccentRailStyle(accent: string, state: NodeVisualState): React.CSSProperties {
  const color =
    state === 'error'
      ? TRACE_COLORS.error
      : state === 'running'
        ? TRACE_COLORS.running
        : state === 'waiting'
          ? TRACE_COLORS.waiting
          : state === 'paused'
            ? TRACE_COLORS.paused
            : accent;
  return { background: color };
}

export function headerActionStyle(visible: boolean, accent: string, active = false): React.CSSProperties {
  return {
    background: active ? `${accent}22` : 'rgba(148, 163, 184, 0.07)',
    border: `1px solid ${active ? `${accent}88` : 'rgba(148, 163, 184, 0.16)'}`,
    borderRadius: 999,
    color: active ? accent : 'var(--muted-foreground)',
    cursor: 'pointer',
    fontSize: 10,
    fontFamily: 'ui-monospace, monospace',
    flexShrink: 0,
    lineHeight: 1.4,
    opacity: visible ? 1 : 0.28,
    padding: '4px 8px',
    transition: 'background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s',
  };
}

const PORT_VALUE_TYPE_COLORS: Record<string, [string, string]> = {
  int: ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  float: ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  number: ['rgba(96, 165, 250, 0.15)', '#93c5fd'],
  str: ['rgba(74, 222, 128, 0.14)', '#86efac'],
  string: ['rgba(74, 222, 128, 0.14)', '#86efac'],
  bool: ['rgba(250, 204, 21, 0.14)', '#fde047'],
  dict: ['rgba(45, 212, 191, 0.14)', '#5eead4'],
  array: ['rgba(56, 189, 248, 0.14)', '#7dd3fc'],
  object: ['rgba(34, 211, 238, 0.14)', '#67e8f9'],
  vector: ['rgba(168, 85, 247, 0.14)', '#c084fc'],
  matrix: ['rgba(129, 140, 248, 0.15)', '#a5b4fc'],
  color: ['rgba(244, 114, 182, 0.14)', '#f9a8d4'],
  binary: ['rgba(148, 163, 184, 0.1)', '#cbd5e1'],
  image: ['rgba(192, 132, 252, 0.14)', '#d8b4fe'],
  latent: ['rgba(129, 140, 248, 0.15)', '#a5b4fc'],
  conditioning: ['rgba(56, 189, 248, 0.14)', '#7dd3fc'],
  model: ['rgba(251, 146, 60, 0.14)', '#fdba74'],
  clip: ['rgba(52, 211, 153, 0.14)', '#6ee7b7'],
  vae: ['rgba(232, 121, 249, 0.14)', '#f0abfc'],
  mask: ['rgba(134, 239, 172, 0.12)', '#bbf7d0'],
  any: ['rgba(148, 163, 184, 0.1)', '#94a3b8'],
};

export function getPortValueTypeColors(valueType: string, fallbackColor = '#94a3b8'): [string, string] {
  return PORT_VALUE_TYPE_COLORS[valueType.toLowerCase()] ?? [`${fallbackColor}1f`, fallbackColor];
}

export function getPortTypeColor(port: SerializedPort, fallbackColor: string, controlColor = '#f472b6'): string {
  if (port.function === 'CONTROL') return controlColor;
  return getPortValueTypeColors(port.valueType, fallbackColor)[1];
}

export function isMutedLinkedInput(port: SerializedPort): boolean {
  return port.direction === 'INPUT' && port.connected === true;
}

export function serializePortValue(value: unknown): string | null {
  if (typeof value === 'string') return value;
  try {
    const serialized = JSON.stringify(value, null, 2);
    return serialized === undefined ? null : serialized;
  } catch {
    return null;
  }
}

export function CopyPortValueButton({
  value,
  align = 'right',
}: {
  value: unknown;
  align?: 'left' | 'right';
}) {
  const [copied, setCopied] = React.useState(false);
  const serialized = serializePortValue(value);
  if (serialized === null) return null;

  return (
    <button
      className="nodrag nopan"
      title={copied ? 'Copied' : 'Copy value to clipboard'}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void navigator.clipboard.writeText(serialized).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 900);
        });
      }}
      onMouseDown={(event) => event.stopPropagation()}
      style={{
        alignItems: 'center',
        background: copied ? 'rgba(74, 222, 128, 0.16)' : 'color-mix(in srgb, var(--node-card-bg) 88%, black)',
        border: `1px solid ${copied ? '#4ade80' : 'rgba(148, 163, 184, 0.28)'}`,
        borderRadius: 7,
        color: copied ? '#4ade80' : 'var(--muted-foreground)',
        cursor: 'pointer',
        display: 'flex',
        height: 22,
        justifyContent: 'center',
        padding: 0,
        position: 'absolute',
        [align]: 8,
        top: 6,
        width: 22,
        zIndex: 3,
      }}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M8 8h10v12H8zM6 16H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

export function PortHoverBadge({
  port,
  align = 'right',
  fallbackColor,
}: {
  port: SerializedPort;
  align?: 'left' | 'right';
  fallbackColor: string;
}) {
  const color = getPortTypeColor(port, fallbackColor);
  const linkState = port.connected ? 'linked' : 'unlinked';
  return (
    <span
      style={{
        background: 'color-mix(in srgb, var(--node-card-bg) 88%, black)',
        border: `1px solid ${color}66`,
        borderRadius: 999,
        boxShadow: '0 8px 18px rgba(2, 6, 23, 0.18)',
        color,
        flexShrink: 0,
        fontFamily: 'ui-monospace, monospace',
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: 0.35,
        lineHeight: 1,
        maxWidth: 128,
        overflow: 'hidden',
        padding: '3px 7px',
        position: 'absolute',
        [align]: 8,
        textOverflow: 'ellipsis',
        textTransform: 'uppercase',
        top: -6,
        whiteSpace: 'nowrap',
        zIndex: 2,
      }}
    >
      {port.valueType} · {linkState}
    </span>
  );
}

export function PortColumnHeader({
  label,
  count,
  align = 'left',
}: {
  label: string;
  count: number;
  align?: 'left' | 'right';
}) {
  return (
    <div
      style={{
        color: 'var(--muted-foreground)',
        display: 'flex',
        fontFamily: 'ui-monospace, monospace',
        fontSize: 9,
        fontWeight: 800,
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
        letterSpacing: 0.8,
        opacity: 0.82,
        padding: '0 10px 2px',
        textTransform: 'uppercase',
      }}
    >
      {label} {count}
    </div>
  );
}

export function StatusBadge({
  state,
  label,
  title,
}: {
  state: Exclude<NodeTraceState, 'idle'>;
  label: string;
  title?: string;
}) {
  const color = TRACE_COLORS[state];
  return (
    <span
      title={title}
      style={{
        background: `${color}1f`,
        border: `1px solid ${color}4d`,
        borderRadius: 999,
        color,
        flexShrink: 0,
        fontFamily: 'ui-monospace, monospace',
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: 0.15,
        lineHeight: 1,
        maxWidth: 96,
        overflow: 'hidden',
        padding: '3px 7px',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
}
