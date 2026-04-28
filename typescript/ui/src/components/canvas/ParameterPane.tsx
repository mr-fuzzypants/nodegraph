/**
 * ParameterPane — right-side inspector panel.
 *
 * Shows the selected node's name, type, and all ports (inputs + outputs)
 * with their value types and current values.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import type { SerializedPort } from '../../types/uiTypes';
import { useTraceStore } from '../../store/traceStore';
import { ScrollArea } from '../ui/scroll-area';
import { Badge } from '../ui/badge';
import { graphClient } from '../../api/graphClient';

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

// ── Semantic colour helpers (data-driven — kept as inline styles) ──────────────

const portDotStyle = (color: string): React.CSSProperties => ({
  width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0,
});

const portTypeBadgeStyle = (color: string): React.CSSProperties => ({
  fontFamily: 'ui-monospace, monospace', fontSize: 9, color,
  border: `1px solid ${color}`, borderRadius: 3, padding: '0 4px', lineHeight: 1.6, flexShrink: 0,
});

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
        background: 'var(--input)',
        border: `1px solid ${hasError ? '#f87171' : 'var(--border)'}`,
        borderRadius: 3,
        color: hasError ? '#f87171' : 'var(--foreground)',
        fontFamily: 'ui-sans-serif, sans-serif',
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
      <div className="px-3 pt-2 pb-0.5 text-[10px] font-bold text-muted-foreground uppercase tracking-widest font-sans">{title}</div>
      {ports.map((p) => {
        const dotColor = PORT_COLORS[p.function] ?? '#9ea3c0';
        const typeColor = valueTypeColor(p.valueType);
        const displayValue = formatValue(p.value);
        const isEditable =
          nodeId &&
          onSetPortValue &&
          p.function === 'DATA' &&
          p.direction === 'INPUT' &&
          !p.connected;

        return (
          <div key={p.name} className="px-3 py-1.5 flex flex-col gap-0.5 border-b border-border/40">
            <div className="flex items-center gap-1.5">
              <div style={portDotStyle(dotColor)} />
              <span className="text-xs text-foreground flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-sans">{p.name}</span>
              <span style={portTypeBadgeStyle(typeColor)}>{p.valueType}</span>
            </div>
            {isEditable ? (
              <InlinePortEditor port={p} onCommit={onSetPortValue!} />
            ) : (
              displayValue !== null && (
                <span className="text-[10px] text-muted-foreground pl-3 overflow-hidden text-ellipsis whitespace-nowrap font-mono" title={String(displayValue)}>
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

// ── NodeIdRow ─────────────────────────────────────────────────────────────────

function NodeIdRow({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [id]);

  return (
    <div
      className="flex items-center gap-1 group cursor-pointer"
      onClick={copy}
      title="Click to copy"
    >
      <span className="text-[10px] text-muted-foreground break-all font-mono select-text flex-1">
        {id}
      </span>
      <span className="shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
        {copied
          ? <Check size={11} className="text-green-400" />
          : <Copy size={11} />}
      </span>
    </div>
  );
}

// ── HumanInputForm ──────────────────────────────────────────────────────────

function HumanInputForm({
  nodeId, prompt, runId, networkId,
}: { nodeId: string; prompt: string; runId: string | null; networkId: string | null }) {
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!response.trim() || !runId || !networkId) return;
    setSubmitting(true);
    try {
      await graphClient.submitHumanInput(runId, networkId, nodeId, response.trim());
      setResponse('');
    } catch { /* stay waiting */ } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="border-t border-border my-2" />
      <div className="mx-3 mb-3">
        <div className="text-[10px] font-mono tracking-widest mb-1.5" style={{ color: '#a78bfa' }}>⌨ AWAITING INPUT</div>
        <div className="text-xs leading-relaxed mb-2 font-sans" style={{ color: 'var(--muted-foreground)' }}>{prompt}</div>
        <textarea
          rows={3}
          value={response}
          placeholder="Type your response…"
          onChange={(e) => setResponse(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); }
          }}
          className="w-full rounded-md text-xs font-sans p-2 resize-none outline-none"
          style={{ background: 'var(--background)', border: '1px solid #a78bfa88', color: 'var(--foreground)', lineHeight: 1.5 }}
        />
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[10px] font-mono" style={{ color: 'var(--muted-foreground)' }}>⌘↵ to submit</span>
          <button
            onClick={submit}
            disabled={submitting || !response.trim()}
            className="text-[10px] font-mono rounded px-2 py-1"
            style={{
              background: response.trim() && !submitting ? '#a78bfa' : 'transparent',
              border: '1px solid #a78bfa',
              color: response.trim() && !submitting ? 'var(--background)' : '#a78bfa',
              cursor: response.trim() && !submitting ? 'pointer' : 'default',
              opacity: submitting ? 0.5 : 1,
            }}
          >
            {submitting ? '…' : 'Submit'}
          </button>
        </div>
      </div>
    </>
  );
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
    <aside className="w-56 bg-background border-l border-border flex flex-col overflow-hidden shrink-0 select-none panel">
      <div className="px-3 pt-2.5 pb-2 border-b border-border shrink-0">
        <span className="block text-xs font-bold text-primary tracking-wide font-sans">Inspector</span>
      </div>

      {!selected ? (
        <div className="text-xs text-muted-foreground p-4 text-center font-sans leading-relaxed">Select a node<br />to inspect it</div>
      ) : (
        <ScrollArea className="flex-1">
          {/* Node identity */}
          <div className="px-3 pt-2.5 pb-2 border-b border-border mb-1">
            <span className="block font-medium text-sm text-foreground overflow-hidden text-ellipsis whitespace-nowrap mb-1.5 font-sans" title={selected.label}>
              {selected.label}
            </span>
            <div className="flex gap-1 flex-wrap">
              <Badge variant="outline" style={{ borderColor: selected.flowType === 'networkNode' ? '#a78bfa' : '#6d7de8', color: selected.flowType === 'networkNode' ? '#a78bfa' : '#6d7de8' }}>
                {selected.flowType === 'networkNode' ? 'NETWORK' : 'FUNCTION'}
              </Badge>
              {selected.isFlowControlNode && (
                <Badge variant="outline" style={{ borderColor: '#f38ba8', color: '#f38ba8' }}>CONTROL</Badge>
              )}
              {selected.subnetworkId && (
                <Badge variant="outline" style={{ borderColor: '#4ade80', color: '#4ade80' }}>SUBGRAPH</Badge>
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
            <div className="border-t border-border my-2" />
          )}
          <PortList ports={selected.outputs} title="Outputs" />

          {/* ── Live trace panels ────────────────────────────────── */}

          {traceInfo?.streamBuffer !== undefined && (
            <>
              <div className="border-t border-border my-2" />
              <div className="mx-3 mb-2">
                <div className="text-[10px] font-mono tracking-widest mb-1" style={{ color: '#8b7355' }}>⟳ STREAMING</div>
                <div className="text-xs font-mono leading-relaxed max-h-36 overflow-y-auto rounded-md p-2"
                  style={{ color: '#e8d5a3', background: '#1a1409', border: '1px solid #5c3a1e', whiteSpace: 'pre-wrap' }}>
                  {traceInfo.streamBuffer || '…'}
                </div>
              </div>
            </>
          )}

          {traceInfo?.agentSteps && traceInfo.agentSteps.length > 0 && (
            <>
              <div className="border-t border-border my-2" />
              <div className="mx-3 mb-2">
                <div className="text-[10px] tracking-widest mb-1" style={{ color: '#8b7355' }}>AGENT STEPS</div>
                {traceInfo.agentSteps.map(step => (
                  <div key={step.step} className="rounded-md p-2 mb-1" style={{ background: '#1a1409', border: '1px solid #3d2a10' }}>
                    <div className="text-[10px] mb-0.5" style={{ color: '#d4a017' }}>
                      Step {step.step} — <span style={{ color: '#a78bfa' }}>{step.tool}</span>
                    </div>
                    <div className="text-[10px]" style={{ color: '#8b7355' }}>in: <span style={{ color: '#c9cce8' }}>{step.input}</span></div>
                    <div className="text-[10px] mt-0.5" style={{ color: '#8b7355' }}>out: <span style={{ color: '#4ade80' }}>{step.output}</span></div>
                  </div>
                ))}
              </div>
            </>
          )}

          {traceInfo?.detail && Object.keys(traceInfo.detail).length > 0 && (
            <>
              <div className="border-t border-border my-2" />
              <div className="mx-3 mb-2 flex flex-wrap gap-1">
                {Object.entries(traceInfo.detail).map(([k, v]) => (
                  <span key={k} className="text-[10px] rounded-sm px-1.5 py-0.5 font-mono" style={{ background: '#1a1409', border: '1px solid #3d2a10', color: '#8b7355' }}>
                    {k}: <span style={{ color: '#d4a017' }}>{String(v)}</span>
                  </span>
                ))}
              </div>
            </>
          )}

          <div className="border-t border-border my-2" />
          <div className="px-3 py-2">
            <span className="block text-[10px] text-muted-foreground mb-0.5 font-sans uppercase tracking-widest">Node ID</span>
            <NodeIdRow id={selected.id} />
          </div>

          {/* ── Human-in-the-loop input ─────────────────────────── */}
          {(traceInfo as any)?.humanInputWaiting && (
            <HumanInputForm
              nodeId={selected.id}
              prompt={(traceInfo as any).humanInputWaiting.prompt}
              runId={(traceInfo as any).humanInputWaiting.runId}
              networkId={(traceInfo as any).humanInputWaiting.networkId}
            />
          )}
        </ScrollArea>
      )}
    </aside>
  );
}
