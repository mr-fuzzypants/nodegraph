import React, { useEffect } from 'react';
import { SplitManager } from './components/canvas/SplitManager';
import { useGraphStore } from './store/graphStore';
import { useTraceSocket } from './hooks/useTraceSocket';
import { useTraceStore } from './store/traceStore';
import { graphClient } from './api/graphClient';
import { Button } from './components/ui/button';
import { ThemeToggle } from './components/ThemeToggle';
import { HugeiconsIcon } from '@hugeicons/react';
import { WorkflowSquare10Icon, PlayIcon, PauseIcon } from '@hugeicons/core-free-icons';

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
    <div className="flex flex-col w-screen h-screen bg-background text-foreground">
      {/* Top bar */}
      <header className="flex items-center px-4 h-10 bg-sidebar border-b border-border gap-3 shrink-0 z-20">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <HugeiconsIcon icon={WorkflowSquare10Icon} className="size-[1.1rem] text-primary" />
          <span className="font-sans font-semibold text-sm text-foreground tracking-wide">
            NodeGraph
          </span>
        </div>

        <div className="w-px h-4 bg-border mx-1" />

        {/* Step mode controls */}
        <Button
          variant={stepModeEnabled ? 'default' : 'outline'}
          size="sm"
          onClick={() => setStepMode(!stepModeEnabled)}
          title={stepModeEnabled ? 'Step mode ON — click to disable' : 'Enable step-by-step execution'}
          className="h-6 px-2.5 text-xs gap-1.5"
        >
          <HugeiconsIcon icon={PauseIcon} className="!size-3" />
          Step Mode
        </Button>

        {isPaused && (
          <Button
            variant="default"
            size="sm"
            onClick={() => graphClient.stepResume()}
            title="Execute next node"
            className="h-6 px-2.5 text-xs gap-1.5"
          >
            <HugeiconsIcon icon={PlayIcon} className="!size-3" />
            Step
          </Button>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {loading && (
          <span className="text-xs text-muted-foreground font-sans">loading…</span>
        )}

        <ThemeToggle />
      </header>

      {/* Error bar */}
      {error && (
        <div
          className="flex items-center justify-between px-4 py-1.5 bg-destructive text-destructive-foreground text-xs font-sans cursor-pointer shrink-0"
          onClick={() => setError(null)}
        >
          <span>⚠ {error}</span>
          <span className="text-destructive-foreground/70">click to dismiss</span>
        </div>
      )}

      {/* Main canvas area — SplitManager owns all panes */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        <SplitManager />
      </div>
    </div>
  );
}
