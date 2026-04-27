import React, { useEffect, useRef } from 'react';
import { useInfoLogStore, type InfoLogEntry, type InfoLogStatus } from '../../store/infoLogStore';
import { useTraceStore } from '../../store/traceStore';

const DEFAULT_HEIGHT = 58;
const MIN_HEIGHT = 38;
const MAX_HEIGHT_RATIO = 0.45;

const statusColor: Record<InfoLogStatus, string> = {
  pending: '#facc15',
  success: '#4ade80',
  error: '#f87171',
  info: '#94a3b8',
};

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function LogRow({ entry }: { entry: InfoLogEntry }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '64px 84px 1fr',
        alignItems: 'baseline',
        gap: 8,
        minWidth: 0,
        lineHeight: '18px',
      }}
    >
      <span style={{ color: '#64748b' }}>{formatTime(entry.timestamp)}</span>
      <span style={{ color: statusColor[entry.status], textTransform: 'uppercase' }}>
        {entry.kind}
      </span>
      <span
        title={entry.message}
        style={{
          color: '#cbd5e1',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
        }}
      >
        {entry.message}
      </span>
    </div>
  );
}

export function InfoPanel() {
  const entries = useInfoLogStore((s) => s.entries);
  const clear = useInfoLogStore((s) => s.clear);
  const latestProgress = useTraceStore((s) => s.latestProgress);
  const [height, setHeight] = React.useState(DEFAULT_HEIGHT);
  const scrollRef = useRef<HTMLDivElement>(null);
  const progressPct = latestProgress ? Math.round(latestProgress.progress * 100) : 0;

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  const handleMouseDown = (event: React.MouseEvent) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = height;

    const onMove = (moveEvent: MouseEvent) => {
      const maxHeight = Math.max(MIN_HEIGHT, window.innerHeight * MAX_HEIGHT_RATIO);
      const nextHeight = startHeight + startY - moveEvent.clientY;
      setHeight(Math.min(maxHeight, Math.max(MIN_HEIGHT, nextHeight)));
    };

    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp, { once: true });
  };

  return (
    <section
      className="panel"
      style={{
        height,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        minHeight: MIN_HEIGHT,
        borderTop: '1px solid var(--border)',
        background: 'var(--background)',
      }}
      aria-label="Info log panel"
    >
      <div
        onMouseDown={handleMouseDown}
        title="Drag to resize info panel"
        style={{
          height: 5,
          flexShrink: 0,
          cursor: 'row-resize',
          background: '#2c2f45',
        }}
      />

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          height: 22,
          padding: '0 10px',
          borderBottom: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: '#94a3b8',
          flexShrink: 0,
        }}
      >
        <span style={{ letterSpacing: 0.6, textTransform: 'uppercase' }}>Info</span>
        <span style={{ color: '#64748b' }}>{entries.length} events</span>
        {latestProgress && (
          <div
            title={latestProgress.message}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              minWidth: 180,
              maxWidth: 360,
              flex: '0 1 360px',
            }}
          >
            <span style={{ color: '#5eead4', whiteSpace: 'nowrap' }}>
              {progressPct}%
            </span>
            <div
              style={{
                flex: 1,
                height: 6,
                borderRadius: 999,
                background: 'rgba(148, 163, 184, 0.16)',
                overflow: 'hidden',
                border: '1px solid rgba(148, 163, 184, 0.14)',
              }}
            >
              <div
                style={{
                  width: `${progressPct}%`,
                  height: '100%',
                  background: '#5eead4',
                  transition: 'width 0.18s ease-out',
                }}
              />
            </div>
            <span
              style={{
                color: '#94a3b8',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                minWidth: 0,
              }}
            >
              {latestProgress.message || 'Running'}
            </span>
          </div>
        )}
        <button
          type="button"
          onClick={clear}
          style={{
            marginLeft: 'auto',
            background: 'transparent',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: 10,
            padding: 0,
          }}
        >
          Clear
        </button>
      </div>

      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '3px 10px 5px',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          minHeight: 0,
        }}
      >
        {entries.length === 0 ? (
          <div style={{ color: '#64748b', lineHeight: '18px' }}>
            API and websocket activity will appear here.
          </div>
        ) : (
          entries.map((entry) => <LogRow key={entry.id} entry={entry} />)
        )}
      </div>
    </section>
  );
}
