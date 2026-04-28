import React, { useEffect, useRef } from 'react';
import { Badge, Box, Button, Group, Progress, ScrollArea, Tabs, Text } from '@mantine/core';
import { useConsoleLogStore, type ConsoleLogEntry } from '../../store/consoleLogStore';
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

const panelContentTextStyle: React.CSSProperties = {
  fontFamily: 'var(--mantine-font-family)',
  fontSize: 10,
  fontWeight: 800,
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
    <Box
      style={{ display: 'grid', gridTemplateColumns: '64px 84px 1fr', alignItems: 'baseline', gap: 8, minWidth: 0, lineHeight: '18px' }}
    >
      <span style={{ ...panelContentTextStyle, color: '#64748b' }}>{formatTime(entry.timestamp)}</span>
      <span style={{ ...panelContentTextStyle, color: statusColor[entry.status], textTransform: 'uppercase' }}>
        {entry.kind}
      </span>
      <span
        title={entry.message}
        style={{
          ...panelContentTextStyle,
          color: '#cbd5e1',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
        }}
      >
        {entry.message}
      </span>
    </Box>
  );
}

function ConsoleRow({ entry }: { entry: ConsoleLogEntry }) {
  const label = entry.nodeName ?? entry.nodeId ?? entry.source;

  return (
    <Box
      style={{ display: 'grid', gridTemplateColumns: '64px minmax(80px, 160px) 1fr', alignItems: 'baseline', gap: 8, minWidth: 0, lineHeight: '18px' }}
    >
      <span style={{ ...panelContentTextStyle, color: '#64748b' }}>{formatTime(entry.timestamp)}</span>
      <span title={label} style={{ ...panelContentTextStyle, color: '#5eead4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
        {label}
      </span>
      <span style={{ ...panelContentTextStyle, color: '#cbd5e1', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', minWidth: 0 }}>
        {entry.message}
      </span>
    </Box>
  );
}

export function InfoPanel() {
  const entries = useInfoLogStore((s) => s.entries);
  const clear = useInfoLogStore((s) => s.clear);
  const consoleEntries = useConsoleLogStore((s) => s.entries);
  const clearConsole = useConsoleLogStore((s) => s.clear);
  const latestProgress = useTraceStore((s) => s.latestProgress);
  const [height, setHeight] = React.useState(DEFAULT_HEIGHT);
  const infoScrollRef = useRef<HTMLDivElement>(null);
  const consoleScrollRef = useRef<HTMLDivElement>(null);
  const progressPct = latestProgress ? Math.round(latestProgress.progress * 100) : 0;

  useEffect(() => {
    const el = infoScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  useEffect(() => {
    const el = consoleScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [consoleEntries.length]);

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
      <Box
        onMouseDown={handleMouseDown}
        title="Drag to resize info panel"
        style={{
          height: 5,
          flexShrink: 0,
          cursor: 'row-resize',
          background: '#2c2f45',
        }}
      />

      <Tabs
        defaultValue="info"
        keepMounted={false}
        style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}
        styles={{
          list: { height: 28, padding: '0 10px', borderBottom: '1px solid var(--border)', flexShrink: 0 },
          tab: {
            height: 28,
            paddingInline: 10,
            fontFamily: 'var(--mantine-font-family)',
            fontSize: 'var(--mantine-font-size-xs)',
            fontWeight: 650,
            color: 'var(--foreground)',
          },
          panel: { flex: 1, minHeight: 0 },
        }}
      >
        <Tabs.List>
          <Tabs.Tab value="info">
            <Group gap={6} wrap="nowrap">
              <Text size="xs" fw={650} c="var(--foreground)" lh={1}>
                Info
              </Text>
              <Badge size="xs" variant="light" color="gray">{entries.length}</Badge>
            </Group>
          </Tabs.Tab>
          <Tabs.Tab value="console">
            <Group gap={6} wrap="nowrap">
              <Text size="xs" fw={650} c="var(--foreground)" lh={1}>
                Console
              </Text>
              <Badge size="xs" variant="light" color="teal">{consoleEntries.length}</Badge>
            </Group>
          </Tabs.Tab>

          {latestProgress && (
            <Group gap={6} wrap="nowrap" ml="md" style={{ minWidth: 180, maxWidth: 360, flex: '0 1 360px' }} title={latestProgress.message}>
              <Text size="xs" ff="monospace" c="teal.3" style={{ whiteSpace: 'nowrap' }}>{progressPct}%</Text>
              <Progress value={progressPct} size={6} radius="xl" color="teal" style={{ flex: 1 }} />
              <Text size="xs" ff="monospace" c="dimmed" truncate style={{ minWidth: 0 }}>
                {latestProgress.message || 'Running'}
              </Text>
            </Group>
          )}
        </Tabs.List>

        <Tabs.Panel value="info">
          <Box style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
            <Group h={22} px={10} gap={8} justify="space-between" style={{ borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
              <Text size="xs" ff="monospace" c="dimmed">{entries.length} trace events</Text>
              <Button variant="subtle" color="gray" size="compact-xs" onClick={clear}>Clear</Button>
            </Group>
            <ScrollArea viewportRef={infoScrollRef} style={{ flex: 1, minHeight: 0 }} styles={{ viewport: { padding: '3px 10px 5px' } }}>
              <Box>
                {entries.length === 0 ? (
                  <Text size="10px" fw={800} c="dimmed" lh="18px">
                    API and websocket activity will appear here.
                  </Text>
                ) : (
                  entries.map((entry) => <LogRow key={entry.id} entry={entry} />)
                )}
              </Box>
            </ScrollArea>
          </Box>
        </Tabs.Panel>

        <Tabs.Panel value="console">
          <Box style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
            <Group h={22} px={10} gap={8} justify="space-between" style={{ borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
              <Text size="xs" ff="monospace" c="dimmed">{consoleEntries.length} console lines</Text>
              <Button variant="subtle" color="gray" size="compact-xs" onClick={clearConsole}>Clear</Button>
            </Group>
            <ScrollArea viewportRef={consoleScrollRef} style={{ flex: 1, minHeight: 0 }} styles={{ viewport: { padding: '3px 10px 5px' } }}>
              <Box>
                {consoleEntries.length === 0 ? (
                  <Text size="10px" fw={800} c="dimmed" lh="18px">
                    Print node output will appear here.
                  </Text>
                ) : (
                  consoleEntries.map((entry) => <ConsoleRow key={entry.id} entry={entry} />)
                )}
              </Box>
            </ScrollArea>
          </Box>
        </Tabs.Panel>
      </Tabs>
    </section>
  );
}
