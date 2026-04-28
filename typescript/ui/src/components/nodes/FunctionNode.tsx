/**
 * FunctionNode — n8n/Griptape-inspired card node for leaf computations.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Handle, Position, NodeProps, Node } from '@xyflow/react';
import type { NodeData, SerializedPort } from '../../types/uiTypes';
import { usePaneStore } from '../canvas/PaneContext';
import { PortValueRenderer } from './PortValueRenderer';
import { useTraceStore } from '../../store/traceStore';
import { getNodeIcon } from '../../lib/nodeIcons';
import { graphClient } from '../../api/graphClient';
import { EditableNodeTitle } from './EditableNodeTitle';
import {
  TRACE_COLORS,
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

// ── Design tokens ─────────────────────────────────────────────────────────────

// Semantic colours (data port teal / control port pink / network accent violet)
const DATA_COL  = '#5eead4';
const CTRL_COL  = '#f472b6';
const ACCENT    = DATA_COL;

// CSS variable shorthands for runtime theme
const CV = {
  bg:        'var(--card)',
  header:    'var(--sidebar)',
  border:    'var(--border)',
  text:      'var(--foreground)',
  muted:     'var(--muted-foreground)',
  portHov:   'rgba(148, 163, 184, 0.10)',
  surface:   'rgba(15, 23, 42, 0.45)',
  shadow:    'none',
};

const TEMPLATE_TOKEN_VALUE_TYPES = ['STRING', 'INT', 'FLOAT', 'BOOL'];

// ── Value-type chip ────────────────────────────────────────────────────────────

function ValueChip({ vt }: { vt: string }) {
  const [bg, fg] = getPortValueTypeColors(vt);
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
        fontFamily: 'ui-sans-serif, sans-serif',
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
  const col = mutedLinkedInput ? CV.muted : getPortTypeColor(port, DATA_COL, CTRL_COL);
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

function isPrimitiveValueType(valueType: string): boolean {
  return ['any', 'int', 'float', 'number', 'str', 'string', 'bool'].includes(valueType.toLowerCase());
}

function valueToEditString(valueType: string, value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parsePrimitivePortInput(
  valueType: string,
  draft: string,
): { ok: boolean; value: any } {
  const vt = valueType.toLowerCase();
  if (draft.trim() === '') return { ok: true, value: null };
  if (vt === 'int') {
    const parsed = parseInt(draft, 10);
    return Number.isNaN(parsed) ? { ok: false, value: null } : { ok: true, value: parsed };
  }
  if (vt === 'float' || vt === 'number') {
    const parsed = parseFloat(draft);
    return Number.isNaN(parsed) ? { ok: false, value: null } : { ok: true, value: parsed };
  }
  if (vt === 'str' || vt === 'string') return { ok: true, value: draft };
  if (vt === 'bool') return { ok: true, value: ['true', '1', 'yes', 'on'].includes(draft.toLowerCase()) };
  try { return { ok: true, value: JSON.parse(draft) }; }
  catch { return { ok: true, value: draft }; }
}

function PrimitiveInputEditor({
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

  useEffect(() => {
    if (!focused) {
      setDraft(valueToEditString(port.valueType, port.value));
      setHasError(false);
    }
  }, [port.value, port.valueType, focused]);

  if (vt === 'bool') {
    const checked = port.value === true || port.value === 1 || port.value === 'true';
    return (
      <label
        className="nodrag nopan"
        onMouseDown={(e) => e.stopPropagation()}
        style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, color: CV.muted, fontSize: 10 }}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCommit(port.name, e.target.checked)}
          style={{ accentColor: DATA_COL, cursor: 'pointer' }}
        />
        value
      </label>
    );
  }

  const commit = () => {
    const { ok, value } = parsePrimitivePortInput(port.valueType, draft);
    if (!ok) {
      setHasError(true);
      return;
    }
    setHasError(false);
    onCommit(port.name, value);
  };

  const isNumeric = vt === 'int' || vt === 'float' || vt === 'number';

  return (
    <input
      className="nodrag nopan"
      type={isNumeric ? 'number' : 'text'}
      step={vt === 'int' ? 1 : isNumeric ? 'any' : undefined}
      value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        setHasError(false);
      }}
      onFocus={() => setFocused(true)}
      onBlur={() => {
        setFocused(false);
        commit();
      }}
      onMouseDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === 'Enter') {
          commit();
          (e.target as HTMLInputElement).blur();
        }
        if (e.key === 'Escape') {
          setDraft(valueToEditString(port.valueType, port.value));
          setHasError(false);
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder={vt === 'int' ? '0' : vt === 'float' || vt === 'number' ? '0.0' : 'value'}
      style={{
        background: 'var(--background)',
        border: `1px solid ${hasError ? '#f87171' : CV.border}`,
        borderRadius: 5,
        color: hasError ? '#f87171' : CV.text,
        flex: '0 1 92px',
        fontFamily: 'ui-monospace, monospace',
        fontSize: 10,
        minWidth: 48,
        outline: 'none',
        padding: '2px 6px',
      }}
      title="Blur or press Enter to save"
    />
  );
}

function InputRow({
  port,
  expanded,
  onSetPortValue,
}: {
  port: SerializedPort;
  expanded: boolean;
  onSetPortValue?: (portName: string, value: any) => void;
}) {
  const [hov, setHov] = useState(false);
  const hasValue = port.value !== null && port.value !== undefined;
  const portColor = getPortTypeColor(port, DATA_COL, CTRL_COL);
  const mutedLinkedInput = isMutedLinkedInput(port);
  const canEdit =
    onSetPortValue &&
    port.function === 'DATA' &&
    port.direction === 'INPUT' &&
    !port.connected &&
    isPrimitiveValueType(port.valueType);
  return (
    <div
      style={{
        background: !expanded || hov ? CV.portHov : 'transparent',
        opacity: hov ? undefined : undefined,
        transition: 'background 0.1s',
        position: 'relative',
        borderRadius: 10,
        height: '100%',
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      {/* Port label row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '7px 10px',
          minHeight: 34,
        }}
      >
        <Handle type="target" position={Position.Left} id={`in-${port.name}`} style={mkHandle(port, 'left')} />
        {!expanded && hov && <PortHoverBadge port={port} fallbackColor={DATA_COL} />}
        {expanded && hov && hasValue && <CopyPortValueButton value={port.value} />}
        <span style={{ color: mutedLinkedInput ? CV.muted : portColor, fontSize: 9, fontWeight: 700, opacity: mutedLinkedInput ? 0.5 : 1, textTransform: 'uppercase' }}>in</span>
        <span style={{ fontSize: 12, color: mutedLinkedInput ? CV.muted : CV.text, flex: 1, fontFamily: 'ui-sans-serif, sans-serif', opacity: mutedLinkedInput ? 0.56 : 1 }}>
          {port.name}
        </span>
        {canEdit ? (
          <PrimitiveInputEditor port={port} onCommit={onSetPortValue} />
        ) : null}
        {expanded && <ValueChip vt={port.valueType} />}
      </div>
      {/* Value panel (shown when expanded) */}
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
  const portColor = getPortTypeColor(port, DATA_COL, CTRL_COL);
  return (
    <div
      style={{
        background: !expanded || hov ? CV.portHov : 'transparent',
        transition: 'background 0.1s',
        position: 'relative',
        borderRadius: 10,
        height: '100%',
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      {/* Port label row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '7px 10px',
          justifyContent: 'flex-end',
          minHeight: 34,
        }}
      >
        {expanded && <ValueChip vt={port.valueType} />}
        {!expanded && hov && <PortHoverBadge port={port} align="left" fallbackColor={DATA_COL} />}
        {expanded && hov && hasValue && <CopyPortValueButton value={port.value} align="left" />}
        <span style={{ color: portColor, fontSize: 9, fontWeight: 700, textTransform: 'uppercase' }}>out</span>
        <span style={{ fontSize: 12, color: CV.text, fontFamily: 'ui-sans-serif, sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {port.name}
        </span>
        <Handle type="source" position={Position.Right} id={`out-${port.name}`} style={mkHandle(port, 'right')} />
      </div>
      {/* Value panel (shown when expanded) */}
      {expanded && hasValue && (
        <div style={{ padding: '0 34px 8px 10px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={ACCENT} />
        </div>
      )}
    </div>
  );
}

// ── Image thumbnail ──────────────────────────────────────────────────────────

function ImageThumbnail({
  url, revisedPrompt, isGenerating, prompt, keepPreviousUrlWhileGenerating = false,
}: {
  url?: string;
  revisedPrompt?: string;
  isGenerating: boolean;
  prompt?: string;
  keepPreviousUrlWhileGenerating?: boolean;
}) {
  const [imgState, setImgState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [lastUrl, setLastUrl] = useState<string | undefined>(undefined);
  const [previewHeight, setPreviewHeight] = useState<number | undefined>(undefined);
  const prevUrlRef = useRef<string | undefined>(undefined);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const displayUrl = url ?? (keepPreviousUrlWhileGenerating && isGenerating ? lastUrl : undefined);

  useEffect(() => {
    if (url) setLastUrl(url);
  }, [url]);

  // Reset load state whenever url changes
  if (displayUrl !== prevUrlRef.current) {
    prevUrlRef.current = displayUrl;
    if (displayUrl) setImgState('loading');
  }

  if (!isGenerating && !displayUrl) return null;

  return (
    <div style={{ borderTop: `1px solid ${CV.border}`, background: CV.header }}>
      {/* Placeholder shown while computing and no url yet */}
      {isGenerating && !displayUrl && (
        <div style={{ padding: 10 }}>
          <div style={{
            width: '100%', height: 140, borderRadius: 6,
            border: `1.5px dashed ${CV.border}`, background: CV.bg,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 6,
          }}>
            <span style={{ fontSize: 22 }}>🎨</span>
            <span style={{ fontSize: 11, color: CV.muted, fontFamily: 'ui-monospace, monospace' }}>Generating…</span>
          </div>
          {prompt && (
            <div style={{
              marginTop: 6, fontSize: 10, color: CV.muted,
              fontFamily: 'ui-sans-serif, sans-serif', lineHeight: 1.4, textAlign: 'center',
              overflow: 'hidden', display: '-webkit-box',
              WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
            } as React.CSSProperties}>
              &ldquo;{prompt}&rdquo;
            </div>
          )}
        </div>
      )}
      {/* Real image */}
      {displayUrl && (
        <div style={{ padding: 8 }}>
          {imgState === 'error' ? (
            <div style={{ color: CV.muted, fontSize: 11, textAlign: 'center', padding: '8px 0', fontFamily: 'ui-monospace, monospace' }}>
              ⚠ image unavailable
            </div>
          ) : (
            <>
              {imgState === 'loading' && (
                <div style={{ height: previewHeight ?? 120, display: 'flex', alignItems: 'center', justifyContent: 'center', color: CV.muted, fontSize: 11, fontFamily: 'ui-monospace, monospace' }}>
                  ⏳ loading…
                </div>
              )}
              <img
                ref={imgRef}
                src={displayUrl}
                alt={revisedPrompt ?? 'Generated image'}
                onLoad={() => {
                  setImgState('loaded');
                  requestAnimationFrame(() => {
                    const height = imgRef.current?.getBoundingClientRect().height;
                    if (height && height > 0) setPreviewHeight(height);
                  });
                }}
                onError={() => setImgState('error')}
                style={{ display: imgState === 'loaded' ? 'block' : 'none', width: '100%', objectFit: 'contain', borderRadius: 6, border: `1px solid ${CV.border}` }}
              />
              {imgState === 'loaded' && revisedPrompt && (
                <div style={{
                  marginTop: 6, fontSize: 10, color: CV.muted,
                  fontFamily: 'ui-sans-serif, sans-serif', lineHeight: 1.4,
                  overflow: 'hidden', display: '-webkit-box',
                  WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                } as React.CSSProperties}>
                  {revisedPrompt}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Inline editable field ─────────────────────────────────────────────────────

type EditMode = 'string' | 'json' | 'auto';

function EditableField({
  label,
  value,
  onSave,
  mode = 'auto',
  rows = 2,
}: {
  label: string;
  value: any;
  onSave: (v: any) => void;
  mode?: EditMode;
  rows?: number;
}) {
  const stringify = (v: any) =>
    typeof v === 'string' ? v : JSON.stringify(v ?? '', null, 2);

  const [text, setText] = useState(() => stringify(value));
  const [focused, setFocused] = useState(false);

  // Sync textarea when external value changes (e.g. after refresh) unless editing
  useEffect(() => {
    if (!focused) setText(stringify(value));
  }, [value, focused]); // eslint-disable-line react-hooks/exhaustive-deps

  const commit = () => {
    if (mode === 'string') {
      onSave(text);
    } else if (mode === 'json') {
      try { onSave(JSON.parse(text)); } catch { /* leave as string so user can fix */ }
    } else {
      // auto: try JSON, fall back to raw string
      try { onSave(JSON.parse(text)); } catch { onSave(text); }
    }
  };

  return (
    <div style={{ padding: '4px 10px 4px 10px' }}>
      <div style={{
        fontSize: 9, color: CV.muted, fontFamily: 'ui-monospace, monospace',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3,
      }}>
        {label}
      </div>
      <textarea
        className="nodrag nopan"
        value={text}
        rows={rows}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); commit(); }}
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            (e.target as HTMLTextAreaElement).blur();
          }
          // prevent ReactFlow drag/keyboard handling while typing
          e.stopPropagation();
        }}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: 'var(--background)',
          color: CV.text,
          border: `1px solid ${focused ? DATA_COL : CV.border}`,
          borderRadius: 5,
          fontSize: 11,
          fontFamily: 'ui-sans-serif, sans-serif',
          padding: '5px 7px',
          resize: 'vertical',
          outline: 'none',
          lineHeight: 1.5,
          transition: 'border-color 0.15s',
        }}
      />
      <div style={{ fontSize: 9, color: CV.muted, marginTop: 2, fontFamily: 'ui-monospace, monospace' }}>
        blur or ⌘↵ to save
      </div>
    </div>
  );
}

// ── Editable body panels for specific node types ───────────────────────────────

function ConstantEditPanel({
  nodeId, port,
}: { nodeId: string; port: SerializedPort | undefined }) {
  const setPortValue = usePaneStore((s) => s.setPortValue);
  if (!port) return null;
  return (
    <div style={{ borderTop: `1px solid ${CV.border}`, background: CV.header }}>
      <EditableField
        label="value"
        value={port.value}
        mode="auto"
        rows={2}
        onSave={(v) => setPortValue(nodeId, port.name, v)}
      />
    </div>
  );
}

function PromptTemplateEditPanel({
  nodeId,
  templatePort,
  variablesPort,
}: {
  nodeId: string;
  templatePort: SerializedPort | undefined;
  variablesPort: SerializedPort | undefined;
}) {
  const setPortValue = usePaneStore((s) => s.setPortValue);
  if (!templatePort && !variablesPort) return null;
  return (
    <div style={{ borderTop: `1px solid ${CV.border}`, background: CV.header }}>
      {templatePort && (
        <EditableField
          label="template"
          value={templatePort.value}
          mode="string"
          rows={3}
          onSave={(v) => setPortValue(nodeId, templatePort.name, v)}
        />
      )}
      {variablesPort && (
        <EditableField
          label="variables (JSON)"
          value={variablesPort.value}
          mode="json"
          rows={3}
          onSave={(v) => setPortValue(nodeId, variablesPort.name, v)}
        />
      )}
    </div>
  );
}

function TemplateStringEditPanel({
  nodeId,
  templatePort,
  tokenPorts,
}: {
  nodeId: string;
  templatePort: SerializedPort | undefined;
  tokenPorts: SerializedPort[];
}) {
  const currentNetworkId = usePaneStore((s) => s.currentNetworkId);
  const refreshNodes = usePaneStore((s) => s.refreshNodes);
  const setPortValue = usePaneStore((s) => s.setPortValue);
  const [name, setName] = useState('');
  const [valueType, setValueType] = useState('STRING');
  const [busyPort, setBusyPort] = useState<string | null>(null);

  const addTokenPort = async () => {
    const trimmed = name.trim();
    if (!currentNetworkId || !trimmed) return;
    setBusyPort('__add__');
    try {
      await graphClient.addDynamicInputPort(currentNetworkId, nodeId, trimmed, valueType);
      setName('');
      await refreshNodes();
    } finally {
      setBusyPort(null);
    }
  };

  const removeTokenPort = async (portName: string) => {
    if (!currentNetworkId) return;
    setBusyPort(portName);
    try {
      await graphClient.removeDynamicInputPort(currentNetworkId, nodeId, portName);
      await refreshNodes();
    } finally {
      setBusyPort(null);
    }
  };

  return (
    <div style={{ borderTop: `1px solid ${CV.border}`, background: CV.header }}>
      {templatePort && (
        <EditableField
          label="tstring"
          value={templatePort.value}
          mode="string"
          rows={3}
          onSave={(v) => setPortValue(nodeId, templatePort.name, v)}
        />
      )}
      <div className="nodrag nopan" style={{ padding: '4px 10px 10px' }}>
        <div style={{
          fontSize: 9, color: CV.muted, fontFamily: 'ui-monospace, monospace',
          textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5,
        }}>
          token inputs
        </div>
        {tokenPorts.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {tokenPorts.map((port) => (
              <button
                key={port.name}
                className="nodrag nopan"
                disabled={busyPort !== null}
                onClick={() => removeTokenPort(port.name)}
                onMouseDown={(event) => event.stopPropagation()}
                style={{
                  background: 'var(--background)',
                  border: `1px solid ${CV.border}`,
                  borderRadius: 999,
                  color: CV.text,
                  cursor: busyPort === null ? 'pointer' : 'default',
                  fontFamily: 'ui-monospace, monospace',
                  fontSize: 10,
                  opacity: busyPort === null || busyPort === port.name ? 1 : 0.45,
                  padding: '3px 8px',
                }}
                title={`Remove ${port.name}`}
              >
                {busyPort === port.name ? 'removing...' : `${port.name} x`}
              </button>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            className="nodrag nopan"
            value={valueType}
            disabled={busyPort !== null}
            onChange={(event) => setValueType(event.target.value)}
            onMouseDown={(event) => event.stopPropagation()}
            style={{ flex: '0 0 82px', background: 'var(--background)', color: CV.text, border: `1px solid ${CV.border}`, borderRadius: 5, fontFamily: 'ui-sans-serif, sans-serif', padding: 4 }}
          >
            {TEMPLATE_TOKEN_VALUE_TYPES.map((type) => (
              <option key={type} value={type} style={{ background: '#020617', color: '#e2e8f0' }}>
                {type.toLowerCase()}
              </option>
            ))}
          </select>
          <input
            className="nodrag nopan"
            value={name}
            disabled={busyPort !== null}
            onChange={(event) => setName(event.target.value)}
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === 'Enter') addTokenPort();
            }}
            placeholder="token name..."
            style={{ flex: 1, minWidth: 0, background: 'var(--background)', color: CV.text, border: `1px solid ${CV.border}`, borderRadius: 5, fontFamily: 'ui-sans-serif, sans-serif', padding: '4px 7px' }}
          />
          <button
            className="nodrag nopan"
            disabled={busyPort !== null || !name.trim()}
            onClick={addTokenPort}
            onMouseDown={(event) => event.stopPropagation()}
            style={{
              background: name.trim() && busyPort === null ? `${DATA_COL}22` : 'transparent',
              border: `1px solid ${DATA_COL}88`,
              borderRadius: 5,
              color: DATA_COL,
              cursor: name.trim() && busyPort === null ? 'pointer' : 'default',
              width: 28,
            }}
            title="Add token input"
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Trace glow colours ────────────────────────────────────────────────────────

const TRACE_GLOW = TRACE_COLORS;

// ── HumanInputPanel ──────────────────────────────────────────────────────────

function HumanInputPanel({
  nodeId,
  prompt,
  runId,
  networkId,
}: {
  nodeId: string;
  prompt: string;
  runId: string | null;
  networkId: string | null;
}) {
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!response.trim() || !runId || !networkId) return;
    setSubmitting(true);
    try {
      await graphClient.submitHumanInput(runId, networkId, nodeId, response.trim());
      setResponse('');
    } catch {
      // stay in waiting state so user can retry
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ borderTop: `1px solid ${CV.border}`, background: CV.header, padding: '8px 10px' }}>
      <div style={{
        fontSize: 9, color: TRACE_GLOW.waiting, fontFamily: 'ui-monospace, monospace',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5,
      }}>
        ⌨ Awaiting input
      </div>
      <div style={{
        fontSize: 11, color: CV.muted, fontFamily: 'ui-sans-serif, sans-serif',
        marginBottom: 6, lineHeight: 1.4,
      }}>
        {prompt}
      </div>
      <textarea
        value={response}
        rows={2}
        placeholder="Type your response…"
        onChange={(e) => setResponse(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            submit();
          }
        }}
        style={{
          width: '100%', boxSizing: 'border-box',
          background: 'var(--background)', color: CV.text,
          border: `1px solid ${TRACE_GLOW.waiting}88`,
          borderRadius: 5, fontSize: 11,
          fontFamily: 'ui-sans-serif, sans-serif',
          padding: '5px 7px', resize: 'none', outline: 'none', lineHeight: 1.5,
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
        <button
          onClick={submit}
          disabled={submitting || !response.trim()}
          style={{
            background: response.trim() && !submitting ? TRACE_GLOW.waiting : 'transparent',
            border: `1px solid ${TRACE_GLOW.waiting}`,
            borderRadius: 5, color: response.trim() && !submitting ? CV.bg : TRACE_GLOW.waiting,
            cursor: response.trim() && !submitting ? 'pointer' : 'default',
            fontSize: 10, padding: '3px 10px',
            fontFamily: 'ui-sans-serif, sans-serif', lineHeight: 1.4,
            transition: 'background 0.1s, color 0.1s', opacity: submitting ? 0.5 : 1,
          }}
        >
          {submitting ? '…' : 'Submit ⌘↵'}
        </button>
      </div>
    </div>
  );
}

function HeaderProgress({
  progress,
  message,
  accent,
}: {
  progress: number;
  message?: string;
  accent: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  return (
    <div style={{ padding: '0 12px 8px', background: CV.header, borderBottom: `1px solid ${CV.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <span style={{ color: accent, fontFamily: 'ui-monospace, monospace', fontSize: 10, fontWeight: 700 }}>
          {pct}%
        </span>
        <span
          title={message}
          style={{
            color: CV.muted,
            fontFamily: 'ui-monospace, monospace',
            fontSize: 10,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {message || 'Sampling'}
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: 'rgba(148, 163, 184, 0.16)', overflow: 'hidden', border: `1px solid ${CV.border}` }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: accent,
            transition: 'width 0.18s ease-out',
          }}
        />
      </div>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FunctionNode({ id, data, selected }: NodeProps<Node<NodeData>>) {
  const executeNode = usePaneStore((s) => s.executeNode);
  const setPortValue = usePaneStore((s) => s.setPortValue);
  const renameNode = usePaneStore((s) => s.renameNode);
  const [runHov, setRunHov] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandHov, setExpandHov] = useState(false);
  const [cardHovered, setCardHovered] = useState(false);

  const traceInfo = useTraceStore((s) => s.nodeStates[id]);

  const onRun = useCallback(() => executeNode(id), [id, executeNode]);

  const inputs = (data.inputs ?? []) as SerializedPort[];
  const outputs = (data.outputs ?? []) as SerializedPort[];
  const hasPorts = inputs.length > 0 || outputs.length > 0;
  const portRowCount = Math.max(inputs.length, outputs.length);

  // Inline editing panels
  const isConstant       = data.nodeType === 'ConstantNode';
  const isPromptTemplate = data.nodeType === 'PromptTemplateNode';
  const isTemplateString = data.nodeType === 'TemplateString';
  const isHumanInput     = data.nodeType === 'HumanInputNode';

  // Icon for this node type
  const NodeIcon = getNodeIcon(data.nodeType as string);

  // Image thumbnail — for nodes that emit an image preview URL in trace detail.
  const isImageGen = data.nodeType === 'ImageGenNode' || data.nodeType === 'ImageGenExecNode';
  const isVaeDecode = data.nodeType === 'VAEDecode';
  const hasImagePreview = isImageGen || isVaeDecode;
  const imageUrl   = typeof traceInfo?.detail?.url === 'string' ? traceInfo.detail.url || undefined : undefined;
  const isGenerating = hasImagePreview && (traceInfo?.state === 'running' || traceInfo?.state === 'pending');
  const promptValue  = inputs.find((p) => p.name === 'prompt')?.value as string | undefined;
  const isDiffusionSampler =
    data.nodeType === 'KSampler' ||
    data.nodeType === 'KSamplerStep' ||
    data.nodeType === 'TiledKSampler';
  const samplerProgress = typeof traceInfo?.progress === 'number' ? traceInfo.progress : undefined;
  const samplerMessage = traceInfo?.progressMessage || traceInfo?.statusMessage;
  const [lastSamplerProgress, setLastSamplerProgress] = useState<number | undefined>(undefined);
  const [lastSamplerMessage, setLastSamplerMessage] = useState<string | undefined>(undefined);
  const isRunning = traceInfo?.state === 'running';
  const hasError = traceInfo?.state === 'error';
  const visualState = getNodeVisualState(traceInfo, selected);
  const actionsVisible = cardHovered || selected || expanded || isRunning || hasError;

  useEffect(() => {
    if (!isDiffusionSampler || samplerProgress === undefined) return;
    setLastSamplerProgress(samplerProgress);
    setLastSamplerMessage(samplerMessage);
  }, [isDiffusionSampler, samplerMessage, samplerProgress]);

  const visibleSamplerProgress = samplerProgress ?? lastSamplerProgress;
  const visibleSamplerMessage = samplerMessage ?? lastSamplerMessage;

  return (
    <div
      className={nodeCardClassName(visualState)}
      onMouseEnter={() => setCardHovered(true)}
      onMouseLeave={() => {
        setCardHovered(false);
        setRunHov(false);
        setExpandHov(false);
      }}
      style={{
        ...nodeCardStyle(DATA_COL),
        minWidth: expanded ? 300 : 375,
        width: '100%',
        height: '100%',
        display: 'flex',
      }}
    >
      <div className="node-accent-rail" style={nodeAccentRailStyle(DATA_COL, visualState)} />
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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
          <NodeIcon size={15.4} color={ACCENT} strokeWidth={2.5} style={{ flexShrink: 0 }} />
          <EditableNodeTitle
            label={data.label as string}
            accent={ACCENT}
            onRename={(name) => renameNode(id, name)}
          />
          {/* Trace status badge */}
          {traceInfo && traceInfo.state === 'done' && traceInfo.durationMs !== undefined && (
            <StatusBadge state="done" label={`${Math.round(traceInfo.durationMs)}ms`} />
          )}
          {traceInfo && traceInfo.state === 'running' && (
            <StatusBadge state="running" label="running" />
          )}
          {isDiffusionSampler && visibleSamplerProgress !== undefined && (
            <StatusBadge state="pending" label={`${Math.round(visibleSamplerProgress * 100)}%`} title={visibleSamplerMessage} />
          )}
          {traceInfo && traceInfo.state === 'paused' && (
            <StatusBadge state="paused" label="paused" />
          )}
          {traceInfo && traceInfo.state === 'waiting' && (
            <StatusBadge state="waiting" label="input" />
          )}
          {traceInfo && traceInfo.state === 'error' && (
            <StatusBadge state="error" label="error" title={traceInfo.error} />
          )}
          {/* Expand toggle */}
          <button
            onClick={() => setExpanded((e) => !e)}
            onMouseEnter={() => setExpandHov(true)}
            onMouseLeave={() => setExpandHov(false)}
            title={expanded ? 'Collapse values' : 'Expand to show values'}
            style={{
              ...headerActionStyle(actionsVisible, DATA_COL, expandHov || expanded),
              color: expandHov || expanded ? DATA_COL : 'var(--muted-foreground)',
            }}
          >
            {expanded ? 'Hide' : 'Show'}
          </button>
          <button
            onClick={onRun}
            onMouseEnter={() => setRunHov(true)}
            onMouseLeave={() => setRunHov(false)}
            style={{
              ...headerActionStyle(actionsVisible, ACCENT, runHov),
              fontWeight: 700,
            }}
            title="Execute this node"
          >
            Run
          </button>
        </div>

        {isDiffusionSampler && visibleSamplerProgress !== undefined && (
          <HeaderProgress progress={visibleSamplerProgress} message={visibleSamplerMessage} accent={ACCENT} />
        )}

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
                    {input ? (
                <InputRow
                        port={input}
                  expanded={expanded}
                  onSetPortValue={(portName, value) => setPortValue(id, portName, value)}
                />
                    ) : (
                      <div style={{ minHeight: 34 }} />
                    )}
                  </div>
                  <div style={{ minWidth: 0, height: '100%' }}>
                    {output ? <OutputRow port={output} expanded={expanded} /> : <div style={{ minHeight: 34 }} />}
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        )}

        {/* Image thumbnail — visible for ImageGen and VAEDecode during and after execution */}
        {hasImagePreview && (
          <ImageThumbnail
            url={imageUrl}
            revisedPrompt={traceInfo?.detail?.revised_prompt as string | undefined}
            isGenerating={isGenerating}
            prompt={promptValue}
            keepPreviousUrlWhileGenerating={isVaeDecode}
          />
        )}

        {/* Inline value editors */}
        {isConstant && (
          <ConstantEditPanel nodeId={id} port={outputs.find((p) => p.name === 'out')} />
        )}
        {isPromptTemplate && (
          <PromptTemplateEditPanel
            nodeId={id}
            templatePort={inputs.find((p) => p.name === 'template')}
            variablesPort={inputs.find((p) => p.name === 'variables')}
          />
        )}
        {isTemplateString && (
          <TemplateStringEditPanel
            nodeId={id}
            templatePort={inputs.find((p) => p.name === 'tstring')}
            tokenPorts={inputs.filter((p) => p.name !== 'tstring')}
          />
        )}
        {isHumanInput && (traceInfo as any)?.humanInputWaiting && (
          <HumanInputPanel
            nodeId={id}
            prompt={(traceInfo as any).humanInputWaiting.prompt}
            runId={(traceInfo as any).humanInputWaiting.runId}
            networkId={(traceInfo as any).humanInputWaiting.networkId}
          />
        )}
      </div>
    </div>
  );
}
