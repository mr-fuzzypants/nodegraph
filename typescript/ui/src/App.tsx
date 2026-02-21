import React, { useEffect } from 'react';
import { SplitManager } from './components/canvas/SplitManager';
import { useGraphStore } from './store/graphStore';
import { useTraceSocket } from './hooks/useTraceSocket';
import { useTraceStore } from './store/traceStore';
import { graphClient } from './api/graphClient';

export default function App() {
  const { init, loading, error, setError } = useGraphStore((s) => ({
    init: s.init,
    loading: s.loading,
    error: s.error,
    setError: s.setError,
  }));

  // Wire trace WebSocket → Zustand store (single connection for all panes)
  const applyEvent = useTraceStore((s) => s.applyEvent);
  useTraceSocket(applyEvent);

  const { stepModeEnabled, setStepMode, isPaused } = useTraceStore((s) => ({
    stepModeEnabled: s.stepModeEnabled,
    setStepMode:     s.setStepMode,
    isPaused:        s.isPaused,
  }));

  useEffect(() => {
    init();
  }, []);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100vw',
        height: '100vh',
        background: '#11121c',
        color: '#c9cce8',
      }}
    >
      {/* Top bar */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '0 16px',
          height: 40,
          background: '#11111b',
          borderBottom: '1px solid #2c2f45',
          gap: 12,
          flexShrink: 0,
          zIndex: 20,
        }}
      >
        <span
          style={{
            fontFamily: 'monospace',
            fontWeight: 'bold',
            fontSize: 14,
            color: '#a78bfa',
            letterSpacing: 1,
          }}
        >
          NodeGraph Editor
        </span>

        {/* Step mode controls */}
        <button
          onClick={() => setStepMode(!stepModeEnabled)}
          style={{
            background: stepModeEnabled ? '#f97316' : 'transparent',
            border: `1px solid ${stepModeEnabled ? '#f97316' : '#4b5280'}`,
            borderRadius: 6, color: stepModeEnabled ? '#11121c' : '#9ca3af',
            cursor: 'pointer', fontSize: 10, padding: '3px 8px',
            fontFamily: 'ui-monospace, monospace', transition: 'all 0.15s',
          }}
          title={stepModeEnabled ? 'Step mode ON — click to disable' : 'Enable step-by-step execution'}
        >
          ⏸ Step Mode
        </button>
        {isPaused && (
          <button
            onClick={() => graphClient.stepResume()}
            style={{
              background: '#f97316', border: '1px solid #f97316',
              borderRadius: 6, color: '#11121c', cursor: 'pointer',
              fontSize: 10, padding: '3px 8px',
              fontFamily: 'ui-monospace, monospace',
            }}
            title="Execute next node"
          >
            ▶ Step
          </button>
        )}

        {loading && (
          <span style={{ marginLeft: 'auto', color: '#fab387', fontFamily: 'monospace', fontSize: 11 }}>
            loading…
          </span>
        )}
      </header>

      {/* Error bar */}
      {error && (
        <div
          style={{
            background: '#f38ba8',
            color: '#11121c',
            padding: '6px 16px',
            fontFamily: 'monospace',
            fontSize: 11,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
            flexShrink: 0,
          }}
          onClick={() => setError(null)}
        >
          ⚠ {error} &nbsp;(click to dismiss)
        </div>
      )}

      {/* Main canvas area — SplitManager owns all panes */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <SplitManager />
      </div>
    </div>
  );
}
