import React, { useCallback, useEffect, useState } from 'react';
import { SplitManager } from './components/canvas/SplitManager';
import { InfoPanel } from './components/canvas/InfoPanel';
import { useGraphStore } from './store/graphStore';
import { useTraceSocket } from './hooks/useTraceSocket';
import { useTraceStore } from './store/traceStore';
import { graphClient } from './api/graphClient';
import type { PaneStore } from './store/paneStore';
import { Button } from './components/ui/button';
import { ThemeToggle } from './components/ThemeToggle';
import { HugeiconsIcon } from '@hugeicons/react';
import { WorkflowSquare10Icon, PlayIcon, PauseIcon } from '@hugeicons/core-free-icons';

function AppMenu({
  onSaveSelection,
}: {
  onSaveSelection: () => void;
}) {
  const [openMenu, setOpenMenu] = useState<'file' | 'edit' | null>(null);

  const menuButtonClass = 'h-6 px-2 rounded text-xs font-sans text-slate-300 hover:bg-slate-800';
  const itemClass = 'block w-full text-left px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800';

  return (
    <nav className="relative flex items-center gap-1" onMouseLeave={() => setOpenMenu(null)}>
      <div className="relative">
        <button
          className={menuButtonClass}
          onClick={() => setOpenMenu(openMenu === 'file' ? null : 'file')}
        >
          File
        </button>
        {openMenu === 'file' && (
          <div className="absolute left-0 top-7 min-w-40 rounded border border-border bg-sidebar shadow-lg py-1 z-50">
            <button
              className={itemClass}
              onClick={() => {
                setOpenMenu(null);
                onSaveSelection();
              }}
            >
              Save Selection
            </button>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          className={menuButtonClass}
          onClick={() => setOpenMenu(openMenu === 'edit' ? null : 'edit')}
        >
          Edit
        </button>
        {openMenu === 'edit' && (
          <div className="absolute left-0 top-7 min-w-32 rounded border border-border bg-sidebar shadow-lg py-1 z-50">
            <button className={`${itemClass} opacity-50 cursor-not-allowed`} disabled>
              No actions yet
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

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
  const [activePaneStore, setActivePaneStore] = useState<PaneStore | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    init();
  }, []);

  const handleActivePaneChange = useCallback((store: PaneStore | null) => {
    setActivePaneStore(store);
  }, []);

  const handleSaveSelection = useCallback(() => {
    if (!activePaneStore) {
      setError('No active graph pane to save from.');
      return;
    }

    const paneState = activePaneStore.getState();
    const selectedCount = paneState.nodes.filter((node) => node.selected && node.deletable !== false).length;
    if (selectedCount === 0) {
      setError('Select at least one node before saving a selection.');
      return;
    }

    const name = window.prompt('Save selected nodes as:', 'selection');
    const trimmedName = name?.trim();
    if (!trimmedName) return;

    paneState.saveSelection(trimmedName)
      .then(() => {
        setSaveMessage(`Saved selection "${trimmedName}"`);
        window.setTimeout(() => setSaveMessage(null), 3000);
      })
      .catch((err) => {
        setError(err?.response?.data?.detail ?? err?.message ?? 'Failed to save selection.');
      });
  }, [activePaneStore, setError]);

  return (
    <div className="flex flex-col w-screen h-screen bg-background text-foreground">
      {/* Top bar */}
      <header className="flex items-center px-4 h-10 bg-sidebar border-b border-border gap-3 shrink-0 z-20 backdrop-blur-md">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <HugeiconsIcon icon={WorkflowSquare10Icon} className="size-[1.1rem] text-primary" />
          <span className="font-sans font-semibold text-sm tracking-wide" style={{ color: '#e2e8f0' }}>
            NodeGraph
          </span>
        </div>

        <div className="w-px h-4 bg-border mx-1" />

        <AppMenu onSaveSelection={handleSaveSelection} />

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

        {saveMessage && (
          <span className="text-xs text-muted-foreground font-sans">{saveMessage}</span>
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
      <div className="flex flex-col flex-1 overflow-hidden min-h-0">
        <SplitManager onActivePaneChange={handleActivePaneChange} />
        <InfoPanel />
      </div>
    </div>
  );
}
