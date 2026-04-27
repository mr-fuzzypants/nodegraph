/**
 * SplitManager — manages a row (or column) of independent graph panes.
 *
 * Features:
 * - Split horizontally or vertically via toolbar buttons
 * - Drag the divider between any two panes to resize them
 * - Close individual panes (minimum one pane always retained)
 * - Each pane navigates the graph independently
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { GraphPane } from './GraphPane';
import { createPaneStore, type PaneStore } from '../../store/paneStore';

// ── Types ──────────────────────────────────────────────────────────────────────

interface PaneEntry {
  id: string;
  store: PaneStore;
}

type Orientation = 'h' | 'v';

const RESIZER_PX = 4;
const MIN_PCT = 8; // minimum pane size in %

// ── Toolbar ────────────────────────────────────────────────────────────────────

function ToolbarBtn({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      title={title}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? '#1e2133' : 'none',
        border: '1px solid #2c2f45',
        borderRadius: 4,
        color: '#9ea3c0',
        cursor: 'pointer',
        fontFamily: 'monospace',
        fontSize: 11,
        padding: '2px 8px',
        lineHeight: 1.6,
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        transition: 'background 0.1s',
      }}
    >
      {children}
    </button>
  );
}

// ── Resizer handle ─────────────────────────────────────────────────────────────

function Resizer({
  orientation,
  onDragStart,
}: {
  orientation: Orientation;
  onDragStart: (e: React.MouseEvent) => void;
}) {
  const [hov, setHov] = useState(false);
  const isH = orientation === 'h';

  return (
    <div
      onMouseDown={onDragStart}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flexShrink: 0,
        width: isH ? RESIZER_PX : '100%',
        height: isH ? '100%' : RESIZER_PX,
        background: hov ? '#a78bfa' : '#2c2f45',
        cursor: isH ? 'col-resize' : 'row-resize',
        transition: 'background 0.12s',
        zIndex: 10,
      }}
    />
  );
}

// ── SplitManager ───────────────────────────────────────────────────────────────

export function SplitManager() {
  // Initialise with one pane
  const [panes, setPanes] = useState<PaneEntry[]>(() => [
    { id: crypto.randomUUID(), store: createPaneStore() },
  ]);
  const [orientation, setOrientation] = useState<Orientation>('h');
  // sizes[i] = flex-grow weight for pane i (all start equal at 1)
  const [sizes, setSizes] = useState<number[]>([1]);

  const containerRef = useRef<HTMLDivElement>(null);
  // Tracks the active drag's removeEventListener so we can clean up on unmount
  const dragCleanupRef = useRef<(() => void) | null>(null);

  // Ensure no ghost drag listeners outlive the component
  useEffect(() => {
    return () => { dragCleanupRef.current?.(); };
  }, []);

  // ── Pane management ──────────────────────────────────────────────────────────

  const splitPane = useCallback(() => {
    const newEntry: PaneEntry = { id: crypto.randomUUID(), store: createPaneStore() };
    setPanes((prev) => [...prev, newEntry]);
    // Give each pane equal weight
    setSizes((prev) => Array(prev.length + 1).fill(1));
  }, []);

  const closePane = useCallback((id: string) => {
    setPanes((prev) => {
      if (prev.length <= 1) return prev; // never close last pane
      const idx = prev.findIndex((p) => p.id === id);
      const next = prev.filter((p) => p.id !== id);
      setSizes((s) => {
        const removed = s[idx];
        const ns = s.filter((_, i) => i !== idx);
        // Distribute removed weight to right neighbour, else left
        const receiver = idx < next.length ? idx : idx - 1;
        ns[receiver] = (ns[receiver] ?? 0) + removed;
        return ns;
      });
      return next;
    });
  }, []);

  const flipOrientation = useCallback(() => {
    setOrientation((o) => (o === 'h' ? 'v' : 'h'));
  }, []);

  // ── Resizing ─────────────────────────────────────────────────────────────────

  const handleResizerMouseDown = useCallback(
    (dividerIdx: number) => (e: React.MouseEvent) => {
      e.preventDefault();
      const container = containerRef.current;
      if (!container) return;

      const isH = orientation === 'h';
      const containerSize = isH
        ? container.clientWidth
        : container.clientHeight;
      const startPos = isH ? e.clientX : e.clientY;
      const startSizes = [...sizes];
      const totalWeight = startSizes.reduce((a, b) => a + b, 0);

      const onMove = (ev: MouseEvent) => {
        const delta = isH ? ev.clientX - startPos : ev.clientY - startPos;
        // Convert px delta → weight delta
        const weightPerPx = totalWeight / containerSize;
        const weightDelta = delta * weightPerPx;

        const ns = [...startSizes];
        ns[dividerIdx] = Math.max(MIN_PCT * weightPerPx * containerSize / 100, startSizes[dividerIdx] + weightDelta);
        ns[dividerIdx + 1] = Math.max(MIN_PCT * weightPerPx * containerSize / 100, startSizes[dividerIdx + 1] - weightDelta);
        setSizes(ns);
      };

      // cleanup removes onMove; called both on mouseup and on component unmount
      const cleanup = () => {
        window.removeEventListener('mousemove', onMove);
        dragCleanupRef.current = null;
      };

      const onUp = () => { cleanup(); };

      dragCleanupRef.current = cleanup;
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp, { once: true });
    },
    [orientation, sizes],
  );

  // ── Render ────────────────────────────────────────────────────────────────────

  const isH = orientation === 'h';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        overflow: 'hidden',
        minWidth: 0,
        minHeight: 0,
      }}
    >
      {/* Global toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 12px',
          background: '#11111b',
          borderBottom: '1px solid #2c2f45',
          flexShrink: 0,
          height: 32,
        }}
      >
        <span
          style={{
            fontFamily: 'monospace',
            fontSize: 11,
            color: '#585b70',
            marginRight: 4,
            letterSpacing: 0.5,
          }}
        >
          Panes
        </span>

        <ToolbarBtn
          onClick={splitPane}
          title={`Split ${isH ? 'right' : 'down'} — add a new pane`}
        >
          {isH ? '⊞ Split Right' : '⊟ Split Down'}
        </ToolbarBtn>

        <ToolbarBtn
          onClick={flipOrientation}
          title="Toggle split orientation"
        >
          {isH ? '↕ Horizontal' : '↔ Vertical'}
        </ToolbarBtn>

        <span
          style={{
            marginLeft: 'auto',
            fontFamily: 'monospace',
            fontSize: 10,
            color: '#535677',
          }}
        >
          {panes.length} {panes.length === 1 ? 'pane' : 'panes'}
        </span>
      </div>

      {/* Panes + resizers */}
      <div
        ref={containerRef}
        style={{
          display: 'flex',
          flexDirection: isH ? 'row' : 'column',
          flex: 1,
          overflow: 'hidden',
          minWidth: 0,
          minHeight: 0,
        }}
      >
        {panes.map((pane, idx) => (
          <React.Fragment key={pane.id}>
            <div
              style={{
                flex: sizes[idx] ?? 1,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                minWidth: 0,
                minHeight: 0,
                borderRight: isH && idx < panes.length - 1 ? 'none' : undefined,
              }}
            >
              <GraphPane
                store={pane.store}
                paneIndex={idx}
                onClose={panes.length > 1 ? () => closePane(pane.id) : undefined}
              />
            </div>

            {/* Resizer between panes */}
            {idx < panes.length - 1 && (
              <Resizer
                orientation={orientation}
                onDragStart={handleResizerMouseDown(idx)}
              />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
