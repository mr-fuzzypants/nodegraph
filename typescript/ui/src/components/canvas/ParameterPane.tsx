/**
 * ParameterPane — right-side inspector panel.
 *
 * Shows the selected node's name, type, and all ports (inputs + outputs)
 * with their value types and current values.
 */
import React, { useState, useEffect } from 'react';
import type { SerializedPort } from '../../types/uiTypes';
import { useTraceStore } from '../../store/traceStore';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface SelectedNodeInfo {
  id: string;
  flowType: string;      // 'functionNode' | 'networkNode'
  label: string;
  inputs: SerializedPort[];
  outputs: SerializedPort[];
  isFlowControlNode: boolean;
  subnetworkId?: string;
}

// ── Colours ────────────────────────────────────────────────────────────────────

const PORT_COLORS: Record<string, string> = {
  DATA:    '#6d7de8',
  CONTROL: '#f38ba8',
};

const VALUE_TYPE_COLORS: Record<string, string> = {
  int:    '#fb923c',
  float:  '#fb923c',
  number: '#fb923c',
  str:    '#4ade80',
  string: '#4ade80',
  bool:   '#fbbf24',
  any:    '#9ea3c0',
};

function valueTypeColor(vt: string): string {
  return VALUE_TYPE_COLORS[vt.toLowerCase()] ?? '#9ea3c0';
}

// ── Styles ─────────────────────────────────────────────────────────────────────

// Dynamic style helpers
const badgeStyle = (color: string): React.CSSProperties => ({
  background: 'transparent',
  border: `1px solid ${color}`,
  borderRadius: 3,
  color: color,
  fontFamily: 'monospace',
  fontSize: 9,
  padding: '1px 5px',
  lineHeight: 1.6,
});

const portDotStyle = (color: string): React.CSSProperties => ({
  width: 7,
  height: 7,
  borderRadius: '50%',
  background: color,
  flexShrink: 0,
});

const portTypeBadgeStyle = (color: string): React.CSSProperties => ({
  fontFamily: 'monospace',
  fontSize: 9,
  color: color,
  border: `1px solid ${color}`,
  borderRadius: 3,
  padding: '0 4px',
  lineHeight: 1.6,
  flexShrink: 0,
});

const S: Record<string, React.CSSProperties> = {
  aside: {
    width: 220,
    background: '#13141f',
    borderLeft: '1px solid #2c2f45',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    userSelect: 'none',
    flexShrink: 0,
  },
  header: {
    padding: '10px 10px 8px',
    borderBottom: '1px solid #2c2f45',
    flexShrink: 0,
  },
  panelTitle: {
    color: '#a78bfa',
    fontFamily: 'monospace',
    fontWeight: 'bold',
    fontSize: 12,
    letterSpacing: 0.5,
    display: 'block',
    marginBottom: 2,
  },
  emptyHint: {
    color: '#535677',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: 16,
    textAlign: 'center',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 0 12px',
  },
  nodeHeader: {
    padding: '6px 10px 10px',
    borderBottom: '1px solid #2c2f45',
    marginBottom: 4,
  },
  nodeLabel: {
    color: '#c9cce8',
    fontFamily: 'monospace',
    fontWeight: 'bold',
    fontSize: 13,
    display: 'block',
    marginBottom: 4,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  badgeRow: {
    display: 'flex',
    gap: 4,
    flexWrap: 'wrap',
  },
  sectionTitle: {
    padding: '6px 10px 4px',
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#535677',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: 'bold',
  },
  portRow: {
    padding: '4px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    borderBottom: '1px solid #1a1d2e',
  },
  portRowTop: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  portName: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#c9cce8',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  portValue: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#535677',
    paddingLeft: 13,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  divider: {
    borderTop: '1px solid #2c2f45',
    margin: '8px 0 4px',
  },
  idBlock: {
    padding: '6px 10px',
    marginTop: 4,
  },
  idLabel: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#535677',
    display: 'block',
    marginBottom: 2,
  },
  idValue: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#535677',
    wordBreak: 'break-all',
    display: 'block',
  },
};

// ── Inline port value editor ─────────────────────────────────────────────────

function valueToEditString(valueType: string, value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parsePortInput(
  valueType: string,
  draft: string,
): { ok: boolean; value: any } {
  const vt = valueType.toLowerCase();
  if (draft.trim() === '') return { ok: true, value: null };
  if (vt === 'int') {
    const n = parseInt(draft, 10);
    return isNaN(n) ? { ok: false, value: null } : { ok: true, value: n };
  }
  if (vt === 'float' || vt === 'number') {
    const n = parseFloat(draft);
    return isNaN(n) ? { ok: false, value: null } : { ok: true, value: n };
  }
  if (vt === 'str' || vt === 'string') return { ok: true, value: draft };
  if (vt === 'vector' || vt === 'list' || vt === 'array') {
    try {
      const arr = JSON.parse(draft);
      return Array.isArray(arr) ? { ok: true, value: arr } : { ok: false, value: null };
    } catch {
      return { ok: false, value: null };
    }
  }
  // 'any' — try JSON, fall back to raw string
  try { return { ok: true, value: JSON.parse(draft) }; }
  catch { return { ok: true, value: draft }; }
}

function InlinePortEditor({
  port,
  onCommit,
}: {
  port: SerializedPort;
  onCommit: (portName: string, value: any) => void;
}) {
  const vt = port.valueType.toLowerCase();
  const [draft, setDraft] = useState(() => valueToEditString(port.valueType, port.value));
  const [focused, setFocused] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Sync from external refresh (e.g. execution) when not focused
  useEffect(() => {
    if (!focused) {
      setDraft(valueToEditString(port.valueType, port.value));
      setHasError(false);
    }
  }, [port.value, port.valueType, focused]);

  if (vt === 'bool') {
    const checked = port.value === true || port.value === 1 || port.value === 'true';
    return (
      <div style={{ paddingLeft: 13, marginTop: 4 }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCommit(port.name, e.target.checked)}
          style={{ cursor: 'pointer', accentColor: '#6d7de8' }}
        />
      </div>
    );
  }

  const commit = () => {
    const { ok, value } = parsePortInput(port.valueType, draft);
    if (ok) {
      setHasError(false);
      onCommit(port.name, value);
    } else {
      setHasError(true);
    }
  };

  const isNumeric = vt === 'int' || vt === 'float' || vt === 'number';

  return (
    <input
      type={isNumeric ? 'number' : 'text'}
      step={vt === 'int' ? 1 : isNumeric ? 'any' : undefined}
      value={draft}
      onChange={(e) => { setDraft(e.target.value); setHasError(false); }}
      onFocus={() => setFocused(true)}
      onBlur={() => { setFocused(false); commit(); }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { commit(); (e.target as HTMLInputElement).blur(); }
        if (e.key === 'Escape') {
          setDraft(valueToEditString(port.valueType, port.value));
          setHasError(false);
          (e.target as HTMLInputElement).blur();
        }
      }}
      style={{
        marginTop: 3,
        background: '#1a1d2e',
        border: `1px solid ${hasError ? '#f87171' : '#2c2f45'}`,
        borderRadius: 3,
        color: hasError ? '#f87171' : '#c9cce8',
        fontFamily: 'ui-monospace, monospace',
        fontSize: 11,
        padding: '2px 5px',
        width: '100%',
        boxSizing: 'border-box',
        outline: 'none',
      }}
      placeholder={vt === 'vector' ? '[1, 2, 3]' : vt === 'int' ? '0' : ''}
    />
  );
}

// ── PortList ───────────────────────────────────────────────────────────────────

function PortList({
  ports,
  title,
  nodeId,
  onSetPortValue,
}: {
  ports: SerializedPort[];
  title: string;
  nodeId?: string;
  onSetPortValue?: (portName: string, value: any) => void;
}) {
  if (ports.length === 0) return null;

  return (
    <>
      <div style={S.sectionTitle}>{title}</div>
      {ports.map((p) => {
        const dotColor = PORT_COLORS[p.function] ?? '#9ea3c0';
        const typeColor = valueTypeColor(p.valueType);
        const displayValue = formatValue(p.value);
        // Show inline editor for unconnected DATA input ports when a set-value callback is provided
        const isEditable =
          nodeId &&
          onSetPortValue &&
          p.function === 'DATA' &&
          p.direction === 'INPUT' &&
          !p.connected;

        return (
          <div key={p.name} style={S.portRow}>
            <div style={S.portRowTop}>
              <div style={portDotStyle(dotColor)} />
              <span style={S.portName}>{p.name}</span>
              <span style={portTypeBadgeStyle(typeColor)}>{p.valueType}</span>
            </div>
            {isEditable ? (
              <InlinePortEditor port={p} onCommit={onSetPortValue!} />
            ) : (
              displayValue !== null && (
                <span style={S.portValue} title={String(displayValue)}>
                  = {displayValue}
                </span>
              )
            )}
          </div>
        );
      })}
    </>
  );
}

function formatValue(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// ── ParameterPane ──────────────────────────────────────────────────────────────

export function ParameterPane({
  selected,
  onSetPortValue,
}: {
  selected: SelectedNodeInfo | null;
  onSetPortValue?: (nodeId: string, portName: string, value: any) => void;
}) {
  const traceInfo = useTraceStore(s => selected ? s.nodeStates[selected.id] : undefined);

  return (
    <aside style={S.aside}>
      <div style={S.header}>
        <span style={S.panelTitle}>Inspector</span>
      </div>

      {!selected ? (
        <div style={S.emptyHint}>Select a node<br />to inspect it</div>
      ) : (
        <div style={S.scrollArea}>
          {/* Node identity */}
          <div style={S.nodeHeader}>
            <span style={S.nodeLabel} title={selected.label}>{selected.label}</span>
            <div style={S.badgeRow}>
              <span style={badgeStyle(selected.flowType === 'networkNode' ? '#a78bfa' : '#6d7de8')}>
                {selected.flowType === 'networkNode' ? 'NETWORK' : 'FUNCTION'}
              </span>
              {selected.isFlowControlNode && (
                <span style={badgeStyle('#f38ba8')}>CONTROL</span>
              )}
              {selected.subnetworkId && (
                <span style={badgeStyle('#a6e3a1')}>SUBGRAPH</span>
              )}
            </div>
          </div>

          {/* Ports */}
          <PortList
            ports={selected.inputs}
            title="Inputs"
            nodeId={selected.id}
            onSetPortValue={
              onSetPortValue
                ? (pn, v) => onSetPortValue(selected.id, pn, v)
                : undefined
            }
          />

          {selected.inputs.length > 0 && selected.outputs.length > 0 && (
              <div style={S.divider} />
            )}
          <PortList ports={selected.outputs} title="Outputs" />

          {/* ── LangChain live panels ──────────────────────────────── */}

          {/* Streaming token buffer — LLMStreamNode */}
          {traceInfo?.streamBuffer !== undefined && (
            <>
              <div style={S.divider} />
              <div style={{ margin: '4px 12px 8px' }}>
                <div style={{ fontSize: 10, color: '#8b7355', marginBottom: 4, fontFamily: 'monospace', letterSpacing: 1 }}>
                  ⟳ STREAMING
                </div>
                <div style={{
                  fontSize: 11, color: '#e8d5a3', fontFamily: 'monospace',
                  whiteSpace: 'pre-wrap', maxHeight: 140, overflowY: 'auto',
                  lineHeight: 1.5, background: '#1a1409',
                  border: '1px solid #5c3a1e', borderRadius: 6, padding: '6px 8px',
                }}>
                  {traceInfo.streamBuffer || '…'}
                </div>
              </div>
            </>
          )}

          {/* Agent tool-call log — ToolAgentNode */}
          {traceInfo?.agentSteps && traceInfo.agentSteps.length > 0 && (
            <>
              <div style={S.divider} />
              <div style={{ margin: '4px 12px 8px' }}>
                <div style={{ fontSize: 10, color: '#8b7355', marginBottom: 4, letterSpacing: 1 }}>
                  AGENT STEPS
                </div>
                {traceInfo.agentSteps.map(step => (
                  <div key={step.step} style={{
                    background: '#1a1409', border: '1px solid #3d2a10',
                    borderRadius: 4, padding: '6px 8px', marginBottom: 4,
                  }}>
                    <div style={{ fontSize: 10, color: '#d4a017', marginBottom: 3 }}>
                      Step {step.step} — <span style={{ color: '#a78bfa' }}>{step.tool}</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#8b7355' }}>
                      in: <span style={{ color: '#c9cce8' }}>{step.input}</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#8b7355', marginTop: 2 }}>
                      out: <span style={{ color: '#4ade80' }}>{step.output}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Detail badge strip — tokens, dimensions, durationMs, etc. */}
          {traceInfo?.detail && Object.keys(traceInfo.detail).length > 0 && (
            <>
              <div style={S.divider} />
              <div style={{ margin: '4px 12px 8px', display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {Object.entries(traceInfo.detail).map(([k, v]) => (
                  <span key={k} style={{
                    fontSize: 10, background: '#1a1409',
                    border: '1px solid #3d2a10', borderRadius: 3,
                    padding: '2px 6px', color: '#8b7355', fontFamily: 'monospace',
                  }}>
                    {k}: <span style={{ color: '#d4a017' }}>{String(v)}</span>
                  </span>
                ))}
              </div>
            </>
          )}

          {/* Node ID (collapsed at bottom) */}
          <div style={S.divider} />
          <div style={S.idBlock}>
            <span style={S.idLabel}>NODE ID</span>
            <span style={S.idValue}>{selected.id}</span>
          </div>
        </div>
      )}
    </aside>
  );
}
