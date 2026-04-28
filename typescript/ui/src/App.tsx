import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SplitManager, type SplitActions } from './components/canvas/SplitManager';
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
import {
  Menu,
  Modal,
  TextInput,
  UnstyledButton,
  Button as MantineButton,
  Group as MantineGroup,
  Stack,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';

/** Matches InfoPanel `Tabs` tab label typography (Info / Console). */
const menuBarTriggerStyle: React.CSSProperties = {
  fontFamily: 'var(--mantine-font-family)',
  fontSize: 'var(--mantine-font-size-xs)',
  fontWeight: 650,
  color: 'var(--foreground)',
  height: 28,
  paddingInline: 12,
  borderRadius: 4,
  display: 'flex',
  alignItems: 'center',
};

const MENU_TRIGGER_CLASS =
  'transition-colors hover:bg-slate-800/90 data-[expanded=true]:bg-slate-800';

function AppMenu({
  onSaveSelection,
  onGroupNodes,
  splitActions,
}: {
  onSaveSelection: () => void;
  onGroupNodes: () => void;
  splitActions: SplitActions | null;
}) {
  return (
    <nav className="relative flex items-center gap-6">
      <Menu
        trigger="click-hover"
        openDelay={0}
        closeDelay={120}
        position="bottom-start"
        offset={4}
        withinPortal
        shadow="md"
      >
        <Menu.Target>
          <UnstyledButton className={MENU_TRIGGER_CLASS} style={menuBarTriggerStyle}>
            File
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={onSaveSelection}>Save Selection…</Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <Menu
        trigger="click-hover"
        openDelay={0}
        closeDelay={120}
        position="bottom-start"
        offset={4}
        withinPortal
        shadow="md"
      >
        <Menu.Target>
          <UnstyledButton className={MENU_TRIGGER_CLASS} style={menuBarTriggerStyle}>
            Edit
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            onClick={onGroupNodes}
            rightSection={<span className="text-[10px] opacity-60">⌘G</span>}
          >
            Group Nodes
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <Menu
        trigger="click-hover"
        openDelay={0}
        closeDelay={120}
        position="bottom-start"
        offset={4}
        withinPortal
        shadow="md"
      >
        <Menu.Target>
          <UnstyledButton className={MENU_TRIGGER_CLASS} style={menuBarTriggerStyle}>
            Window
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            disabled={!splitActions}
            onClick={() => splitActions?.splitRight()}
          >
            Split Right
          </Menu.Item>
          <Menu.Item
            disabled={!splitActions}
            onClick={() => splitActions?.splitDown()}
          >
            Split Vertical
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
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
  const [splitActions, setSplitActions] = useState<SplitActions | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // Save-selection modal state
  const [saveModalOpened, { open: openSaveModal, close: closeSaveModal }] =
    useDisclosure(false);
  const [saveName, setSaveName] = useState('selection');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    init();
  }, []);

  const handleActivePaneChange = useCallback((store: PaneStore | null) => {
    setActivePaneStore(store);
  }, []);

  const handleSplitActionsChange = useCallback((actions: SplitActions) => {
    setSplitActions(actions);
  }, []);

  const handleSaveSelection = useCallback(() => {
    if (!activePaneStore) {
      setError('No active graph pane to save from.');
      return;
    }

    const paneState = activePaneStore.getState();
    const selectedCount = paneState.nodes.filter(
      (node) => node.selected && node.deletable !== false,
    ).length;
    if (selectedCount === 0) {
      setError('Select at least one node before saving a selection.');
      return;
    }

    setSaveName('selection');
    openSaveModal();
  }, [activePaneStore, openSaveModal, setError]);

  const handleConfirmSave = useCallback(() => {
    if (!activePaneStore) return;
    const trimmedName = saveName.trim();
    if (!trimmedName) return;

    const paneState = activePaneStore.getState();
    setSaving(true);
    paneState
      .saveSelection(trimmedName)
      .then(() => {
        setSaveMessage(`Saved selection "${trimmedName}"`);
        window.setTimeout(() => setSaveMessage(null), 3000);
        closeSaveModal();
      })
      .catch((err) => {
        setError(
          err?.response?.data?.detail ??
            err?.message ??
            'Failed to save selection.',
        );
      })
      .finally(() => {
        setSaving(false);
      });
  }, [activePaneStore, saveName, closeSaveModal, setError]);

  const handleGroupNodes = useCallback(() => {
    if (!activePaneStore) {
      setError('No active graph pane.');
      return;
    }
    const paneState = activePaneStore.getState();
    const groupable = paneState.nodes.filter(
      (n) => n.selected && n.deletable !== false,
    );
    if (groupable.length === 0) {
      setError('Select at least one node before grouping.');
      return;
    }
    void paneState.groupNodes(groupable.map((node) => node.id));
  }, [activePaneStore, setError]);

  const saveModalTitle = useMemo(() => 'Save Selection', []);

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

        <AppMenu
          onSaveSelection={handleSaveSelection}
          onGroupNodes={handleGroupNodes}
          splitActions={splitActions}
        />

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
        <SplitManager
          onActivePaneChange={handleActivePaneChange}
          onActionsChange={handleSplitActionsChange}
        />
        <InfoPanel />
      </div>

      {/* Save Selection modal */}
      <Modal
        opened={saveModalOpened}
        onClose={closeSaveModal}
        title={saveModalTitle}
        centered
        size="sm"
        overlayProps={{ backgroundOpacity: 0.55, blur: 2 }}
      >
        <Stack gap="sm">
          <TextInput
            label="Save selection as"
            placeholder="selection"
            value={saveName}
            onChange={(event) => setSaveName(event.currentTarget.value)}
            data-autofocus
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                handleConfirmSave();
              }
            }}
          />
          <MantineGroup justify="flex-end" gap="xs">
            <MantineButton variant="subtle" onClick={closeSaveModal} disabled={saving}>
              Cancel
            </MantineButton>
            <MantineButton
              onClick={handleConfirmSave}
              loading={saving}
              disabled={!saveName.trim()}
            >
              Save
            </MantineButton>
          </MantineGroup>
        </Stack>
      </Modal>
    </div>
  );
}
