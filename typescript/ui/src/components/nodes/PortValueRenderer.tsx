/**
 * PortValueRenderer — type-aware inline renderers for port values.
 *
 * Renderers:
 *   number / int / float  → styled numeric display with unit hint
 *   str / string          → monospace text block (scrollable)
 *   bool                  → coloured TRUE / FALSE pill
 *   matrix                → compact cell grid (value[][])
 *   list / array          → vertical pill list
 *   json / any            → collapsible JSON view
 *   null / undefined      → dim "—" placeholder
 */
import React, { useState } from 'react';

// ── Palette (matches node card tokens) ────────────────────────────────────────

const P = {
  bg:       '#11121c',
  border:   '#23263a',
  text:     '#c9cce8',
  muted:    '#4b5280',
  trueCol:  '#34d399',
  falseCol: '#f87171',
  numCol:   '#60a5fa',
  strCol:   '#34d399',
  nullCol:  '#535677',
};

// ── Detect which renderer to use ──────────────────────────────────────────────

type RenderMode = 'null' | 'number' | 'string' | 'bool' | 'matrix' | 'list' | 'json';

function detectMode(valueType: string, value: unknown): RenderMode {
  if (value === null || value === undefined) return 'null';
  const vt = valueType.toLowerCase();
  if (vt === 'int' || vt === 'float' || vt === 'number') return 'number';
  if (vt === 'str' || vt === 'string') return 'string';
  if (vt === 'bool') return 'bool';
  if (vt === 'matrix') return 'matrix';
  if (
    vt === 'list' || vt === 'array' ||
    (vt === 'any' && Array.isArray(value) && !Array.isArray((value as unknown[])[0]))
  ) return 'list';
  if (Array.isArray(value) && Array.isArray((value as unknown[][])[0])) return 'matrix';
  if (Array.isArray(value)) return 'list';
  return 'json';
}

// ── Individual renderers ───────────────────────────────────────────────────────

function NullDisplay() {
  return (
    <span style={{ color: P.nullCol, fontFamily: 'ui-monospace, monospace', fontSize: 11 }}>
      —
    </span>
  );
}

function NumberDisplay({ value }: { value: unknown }) {
  const n = Number(value);
  const isInt = Number.isInteger(n);
  return (
    <span
      style={{
        fontFamily: 'ui-monospace, monospace',
        fontSize: 13,
        fontWeight: 700,
        color: P.numCol,
        letterSpacing: 0.3,
      }}
    >
      {isInt ? n.toLocaleString() : n.toPrecision(6).replace(/\.?0+$/, '')}
    </span>
  );
}

function StringDisplay({ value }: { value: unknown }) {
  const s = String(value);
  const multiline = s.includes('\n');
  return (
    <span
      style={{
        display: 'block',
        fontFamily: 'ui-monospace, monospace',
        fontSize: 11,
        color: P.strCol,
        whiteSpace: multiline ? 'pre-wrap' : 'pre',
        wordBreak: 'break-all',
        maxHeight: 80,
        overflowY: 'auto',
        lineHeight: 1.5,
      }}
    >
      {s}
    </span>
  );
}

function BoolDisplay({ value }: { value: unknown }) {
  const b = value === true || value === 'true' || value === 1;
  return (
    <span
      style={{
        fontFamily: 'ui-monospace, monospace',
        fontSize: 11,
        fontWeight: 700,
        color: b ? P.trueCol : P.falseCol,
        border: `1px solid ${b ? P.trueCol : P.falseCol}`,
        borderRadius: 4,
        padding: '2px 8px',
        letterSpacing: 0.5,
        textTransform: 'uppercase',
      }}
    >
      {b ? 'TRUE' : 'FALSE'}
    </span>
  );
}

function MatrixDisplay({ value }: { value: unknown }) {
  const rows = value as unknown[][];
  if (!Array.isArray(rows) || rows.length === 0) return <NullDisplay />;

  const cols = Math.max(...rows.map((r) => (Array.isArray(r) ? r.length : 0)));
  if (cols === 0) return <NullDisplay />;

  // colour-map value magnitude for heatmap effect
  const allVals = rows.flat().map(Number).filter((v) => !isNaN(v));
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const range = max - min || 1;

  function cellBg(v: unknown) {
    const n = Number(v);
    if (isNaN(n)) return P.border;
    const t = (n - min) / range; // 0–1
    // interpolate #172554 → #60a5fa
    const r = Math.round(0x17 + t * (0x60 - 0x17));
    const g = Math.round(0x25 + t * (0xa5 - 0x25));
    const b = Math.round(0x54 + t * (0xfa - 0x54));
    return `rgb(${r},${g},${b})`;
  }

  const MAX_ROWS = 8;
  const MAX_COLS = 8;
  const displayRows = rows.slice(0, MAX_ROWS);
  const truncatedRows = rows.length > MAX_ROWS;
  const truncatedCols = cols > MAX_COLS;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          borderCollapse: 'collapse',
          fontFamily: 'ui-monospace, monospace',
          fontSize: 9,
        }}
      >
        <tbody>
          {displayRows.map((row, ri) => (
            <tr key={ri}>
              {(Array.isArray(row) ? row.slice(0, MAX_COLS) : []).map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    background: cellBg(cell),
                    color: '#e2e8f0',
                    padding: '2px 4px',
                    minWidth: 28,
                    textAlign: 'right',
                    border: `1px solid ${P.bg}`,
                    borderRadius: 2,
                  }}
                  title={String(cell)}
                >
                  {typeof cell === 'number'
                    ? Number.isInteger(cell) ? cell : cell.toPrecision(3)
                    : String(cell)}
                </td>
              ))}
              {truncatedCols && (
                <td style={{ color: P.muted, padding: '2px 4px', fontSize: 8 }}>…</td>
              )}
            </tr>
          ))}
          {truncatedRows && (
            <tr>
              <td
                colSpan={Math.min(cols, MAX_COLS) + 1}
                style={{ color: P.muted, padding: '2px 4px', fontSize: 8, textAlign: 'center' }}
              >
                ⋮ {rows.length - MAX_ROWS} more rows
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div style={{ color: P.muted, fontSize: 9, marginTop: 2 }}>
        {rows.length}×{cols}
      </div>
    </div>
  );
}

function ListDisplay({ value }: { value: unknown }) {
  const items = Array.isArray(value) ? value : [value];
  const MAX = 12;
  const shown = items.slice(0, MAX);
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        maxHeight: 100,
        overflowY: 'auto',
      }}
    >
      {shown.map((item, i) => (
        <span
          key={i}
          style={{
            fontFamily: 'ui-monospace, monospace',
            fontSize: 10,
            color: P.text,
            background: P.border,
            borderRadius: 3,
            padding: '1px 6px',
            whiteSpace: 'pre',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '100%',
          }}
          title={JSON.stringify(item)}
        >
          [{i}] {typeof item === 'object' ? JSON.stringify(item) : String(item)}
        </span>
      ))}
      {items.length > MAX && (
        <span style={{ color: P.muted, fontSize: 9 }}>… +{items.length - MAX} more</span>
      )}
    </div>
  );
}

function JsonDisplay({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  const str = JSON.stringify(value, null, 2);
  const preview = JSON.stringify(value);
  const short = preview.length <= 40 ? preview : preview.slice(0, 40) + '…';

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: 'none',
          border: 'none',
          color: P.muted,
          cursor: 'pointer',
          fontFamily: 'ui-monospace, monospace',
          fontSize: 10,
          padding: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <span style={{ fontSize: 8 }}>{open ? '▼' : '▶'}</span>
        <span style={{ color: P.text }}>{short}</span>
      </button>
      {open && (
        <pre
          style={{
            marginTop: 4,
            background: P.bg,
            border: `1px solid ${P.border}`,
            borderRadius: 4,
            padding: '6px 8px',
            fontFamily: 'ui-monospace, monospace',
            fontSize: 10,
            color: P.text,
            maxHeight: 120,
            overflowY: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {str}
        </pre>
      )}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

export interface PortValueRendererProps {
  valueType: string;
  value: unknown;
  /** Accent colour to match the parent node card (blue or violet) */
  accentColor?: string;
}

export function PortValueRenderer({ valueType, value, accentColor }: PortValueRendererProps) {
  const mode = detectMode(valueType, value);

  return (
    <div
      style={{
        marginTop: 4,
        marginBottom: 2,
        padding: '6px 8px',
        background: P.bg,
        border: `1px solid ${accentColor ? `${accentColor}33` : P.border}`,
        borderRadius: 5,
        overflow: 'hidden',
      }}
    >
      {mode === 'null'   && <NullDisplay />}
      {mode === 'number' && <NumberDisplay value={value} />}
      {mode === 'string' && <StringDisplay value={value} />}
      {mode === 'bool'   && <BoolDisplay value={value} />}
      {mode === 'matrix' && <MatrixDisplay value={value} />}
      {mode === 'list'   && <ListDisplay value={value} />}
      {mode === 'json'   && <JsonDisplay value={value} />}
    </div>
  );
}
