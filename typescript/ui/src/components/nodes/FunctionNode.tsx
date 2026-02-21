/**
 * FunctionNode — n8n/Griptape-inspired card node for leaf computations.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Handle, Position, NodeProps, Node, NodeResizer } from '@xyflow/react';
import type { NodeData, SerializedPort } from '../../types/uiTypes';
import { usePaneStore } from '../canvas/PaneContext';
import { PortValueRenderer } from './PortValueRenderer';
import { useTraceStore } from '../../store/traceStore';

// ── Design tokens ─────────────────────────────────────────────────────────────

const T = {
  bg:         '#1a1b26',
  header:     '#13141f',
  border:     '#2c2f45',
  borderSel:  '#6d7de8',
  accent:     '#6d7de8',
  shadow:     '0 4px 20px rgba(0,0,0,0.6), 0 1px 4px rgba(0,0,0,0.4)',
  shadowSel:  '0 0 0 2px #6d7de8, 0 6px 24px rgba(109,125,232,0.4)',
  text:       '#e2e8f0',
  muted:      '#6b7280',
  portHov:    '#1e2133',
  handleData: '#6d7de8',
  handleCtrl: '#f87171',
};

// ── Value-type chip ────────────────────────────────────────────────────────────

const CHIP_COLORS: Record<string, [string, string]> = {
  int:    ['#172554', '#60a5fa'],
  float:  ['#172554', '#60a5fa'],
  number: ['#172554', '#60a5fa'],
  str:    ['#052e16', '#34d399'],
  string: ['#052e16', '#34d399'],
  bool:   ['#422006', '#fbbf24'],
  any:    ['#1f2133', '#6b7280'],
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
      {/* Port label row */}
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
      {/* Value panel (shown when expanded) */}
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
      {/* Port label row */}
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
      {/* Value panel (shown when expanded) */}
      {expanded && hasValue && (
        <div style={{ padding: '0 18px 6px 12px' }}>
          <PortValueRenderer valueType={port.valueType} value={port.value} accentColor={T.accent} />
        </div>
      )}
    </div>
  );
}

// ── Image thumbnail ──────────────────────────────────────────────────────────

function ImageThumbnail({
  url, revisedPrompt, isGenerating, prompt,
}: {
  url?: string;
  revisedPrompt?: string;
  isGenerating: boolean;
  prompt?: string;
}) {
  const [imgState, setImgState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const prevUrlRef = useRef<string | undefined>(undefined);
  // Reset load state whenever url changes
  if (url !== prevUrlRef.current) {
    prevUrlRef.current = url;
    if (url) setImgState('loading');
  }

  if (!isGenerating && !url) return null;

  return (
    <div style={{ borderTop: `1px solid ${T.border}`, background: T.header }}>
      {/* Placeholder shown while computing and no url yet */}
      {isGenerating && !url && (
        <div style={{ padding: 10 }}>
          <div style={{
            width: '100%',
            height: 140,
            borderRadius: 6,
            border: `1.5px dashed ${T.border}`,
            background: T.bg,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
          }}>
            <span style={{ fontSize: 22 }}>🎨</span>
            <span style={{
              fontSize: 11, color: T.muted,
              fontFamily: 'ui-monospace, monospace',
            }}>Generating…</span>
          </div>
          {prompt && (
            <div style={{
              marginTop: 6, fontSize: 10, color: T.muted,
              fontFamily: 'ui-sans-serif, sans-serif',
              lineHeight: 1.4, textAlign: 'center',
              overflow: 'hidden',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            } as React.CSSProperties}>
              &ldquo;{prompt}&rdquo;
            </div>
          )}
        </div>
      )}
      {/* Real image */}
      {url && (
        <div style={{ padding: 8 }}>
          {imgState === 'error' ? (
            <div style={{
              color: T.muted, fontSize: 11, textAlign: 'center',
              padding: '8px 0', fontFamily: 'ui-monospace, monospace',
            }}>
              ⚠ image unavailable
            </div>
          ) : (
            <>
              {imgState === 'loading' && (
                <div style={{
                  height: 120, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', color: T.muted,
                  fontSize: 11, fontFamily: 'ui-monospace, monospace',
                }}>
                  ⏳ loading…
                </div>
              )}
              <img
                src={url}
                alt={revisedPrompt ?? 'Generated image'}
                onLoad={() => setImgState('loaded')}
                onError={() => setImgState('error')}
                style={{
                  display: imgState === 'loaded' ? 'block' : 'none',
                  width: '100%',
                  objectFit: 'contain',
                  borderRadius: 6,
                  border: `1px solid ${T.border}`,
                }}
              />
              {imgState === 'loaded' && revisedPrompt && (
                <div style={{
                  marginTop: 6, fontSize: 10, color: T.muted,
                  fontFamily: 'ui-sans-serif, sans-serif',
                  lineHeight: 1.4, overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
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
        fontSize: 9, color: T.muted, fontFamily: 'ui-monospace, monospace',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3,
      }}>
        {label}
      </div>
      <textarea
        value={text}
        rows={rows}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); commit(); }}
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
          background: '#0d0e17',
          color: T.text,
          border: `1px solid ${focused ? T.accent : T.border}`,
          borderRadius: 5,
          fontSize: 11,
          fontFamily: 'ui-monospace, monospace',
          padding: '5px 7px',
          resize: 'vertical',
          outline: 'none',
          lineHeight: 1.5,
          transition: 'border-color 0.15s',
        }}
      />
      <div style={{ fontSize: 9, color: T.muted, marginTop: 2, fontFamily: 'ui-monospace, monospace' }}>
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
    <div style={{ borderTop: `1px solid ${T.border}`, background: T.header }}>
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
    <div style={{ borderTop: `1px solid ${T.border}`, background: T.header }}>
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

// ── Trace glow colours ────────────────────────────────────────────────────────

const TRACE_GLOW: Record<string, string> = {
  pending: '#818cf8',
  running: '#facc15',
  paused:  '#f97316',
  done:    '#4ade80',
  error:   '#f87171',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function FunctionNode({ id, data, selected }: NodeProps<Node<NodeData>>) {
  const executeNode = usePaneStore((s) => s.executeNode);
  const [runHov, setRunHov] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandHov, setExpandHov] = useState(false);

  const traceInfo = useTraceStore((s) => s.nodeStates[id]);
  const glowColor = traceInfo ? TRACE_GLOW[traceInfo.state] : undefined;
  const traceShadow = glowColor
    ? `0 0 0 1.5px ${glowColor}, 0 0 18px ${glowColor}88`
    : undefined;
  const baseShadow = selected ? T.shadowSel : T.shadow;
  const cardShadow = traceShadow ? `${traceShadow}, ${baseShadow}` : baseShadow;

  const onRun = useCallback(() => executeNode(id), [id, executeNode]);

  const inputs = (data.inputs ?? []) as SerializedPort[];
  const outputs = (data.outputs ?? []) as SerializedPort[];
  const hasPorts = inputs.length > 0 || outputs.length > 0;

  // Inline editing panels
  const isConstant       = data.nodeType === 'ConstantNode';
  const isPromptTemplate = data.nodeType === 'PromptTemplateNode';

  // Image thumbnail — only for ImageGenNode
  const isImageGen = data.nodeType === 'ImageGenNode';
  const imageUrl   = typeof traceInfo?.detail?.url === 'string' ? traceInfo.detail.url || undefined : undefined;
  const isGenerating = isImageGen && (traceInfo?.state === 'running' || traceInfo?.state === 'pending');
  const promptValue  = inputs.find((p) => p.name === 'prompt')?.value as string | undefined;

  return (
    <div
      style={{
        background: T.bg,
        border: `1.5px solid ${selected ? T.borderSel : T.border}`,
        borderRadius: 10,
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        boxShadow: cardShadow,
        transition: 'box-shadow 0.15s, border-color 0.15s',
        display: 'flex',
      }}
    >
      <NodeResizer
        minWidth={220}
        minHeight={60}
        isVisible={selected}
        lineStyle={{ border: '1.5px solid #6d7de8' }}
        handleStyle={{
          width: 10, height: 10, borderRadius: 3,
          background: '#6d7de8', border: '2px solid #1a1b26',
        }}
      />

      {/* Left accent bar */}
      <div style={{ width: 4, background: T.accent, flexShrink: 0, borderRadius: '10px 0 0 10px' }} />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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
          <div style={{
            width: 9, height: 9, borderRadius: '50%', background: T.accent,
            boxShadow: `0 0 8px ${T.accent}`, flexShrink: 0,
          }} />
          <span style={{
            fontWeight: 700, fontSize: 13, color: T.text, flex: 1,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            fontFamily: 'ui-sans-serif, sans-serif',
          }}>
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
          {/* Expand toggle */}
          <button
            onClick={() => setExpanded((e) => !e)}
            onMouseEnter={() => setExpandHov(true)}
            onMouseLeave={() => setExpandHov(false)}
            title={expanded ? 'Collapse values' : 'Expand to show values'}
            style={{
              background: expandHov ? '#1e2133' : 'transparent',
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
          <button
            onClick={onRun}
            onMouseEnter={() => setRunHov(true)}
            onMouseLeave={() => setRunHov(false)}
            style={{
              background: runHov ? T.accent : 'transparent',
              border: `1px solid ${T.accent}`,
              borderRadius: 6,
              color: runHov ? T.bg : T.accent,
              cursor: 'pointer',
              fontSize: 10,
              padding: '3px 8px',
              fontFamily: 'ui-monospace, monospace',
              flexShrink: 0,
              transition: 'background 0.1s, color 0.1s',
              lineHeight: 1.4,
            }}
            title="Execute this node"
          >
            ▶ Run
          </button>
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

        {/* Image thumbnail — visible for ImageGenNode during and after execution */}
        {isImageGen && (
          <ImageThumbnail
            url={imageUrl}
            revisedPrompt={traceInfo?.detail?.revised_prompt as string | undefined}
            isGenerating={isGenerating}
            prompt={promptValue}
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
      </div>
    </div>
  );
}
