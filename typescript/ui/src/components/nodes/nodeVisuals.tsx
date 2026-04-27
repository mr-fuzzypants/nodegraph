import React from 'react';
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
