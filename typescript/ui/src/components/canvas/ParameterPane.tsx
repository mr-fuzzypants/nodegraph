/**
 * ParameterPane — right-side inspector panel.
 *
 * Shows the selected node's name, type, and all ports (inputs + outputs)
 * with their value types and current values.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Center,
  Checkbox,
  Code,
  Divider,
  Group,
  Kbd,
  NumberInput,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core';
import type { SerializedPort } from '../../types/uiTypes';
import { useTraceStore } from '../../store/traceStore';
import { graphClient } from '../../api/graphClient';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface SelectedNodeInfo {
  id: string;
  flowType: string;      // 'functionNode' | 'networkNode'
  label: string;
  inputs: SerializedPort[];
  outputs: SerializedPort[];
  isFlowControlNode: boolean;
  subnetworkId?: string;
}

// ── Colours ────────────────────────────────────────────────────────────────────

const PORT_COLORS: Record<string, string> = {
  DATA:    '#6d7de8',
  CONTROL: '#f38ba8',
};

const VALUE_TYPE_COLORS: Record<string, string> = {
  int:    '#fb923c',
  float:  '#fb923c',
  number: '#fb923c',
  str:    '#4ade80',
  string: '#4ade80',
  bool:   '#fbbf24',
  any:    '#9ea3c0',
};

function valueTypeColor(vt: string): string {
  return VALUE_TYPE_COLORS[vt.toLowerCase()] ?? '#9ea3c0';
}

// ── Semantic colour helpers (data-driven — kept as inline styles) ──────────────

const portDotStyle = (color: string): React.CSSProperties => ({
  width: 8,
  height: 8,
  borderRadius: '50%',
  background: color,
  boxShadow: `0 0 14px ${color}66`,
  flexShrink: 0,
});

// ── Inline port value editor ─────────────────────────────────────────────────

function valueToEditString(valueType: string, value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parsePortInput(
  valueType: string,
  draft: string,
): { ok: boolean; value: any } {
  const vt = valueType.toLowerCase();
  if (draft.trim() === '') return { ok: true, value: null };
  if (vt === 'int') {
    const n = parseInt(draft, 10);
    return isNaN(n) ? { ok: false, value: null } : { ok: true, value: n };
  }
  if (vt === 'float' || vt === 'number') {
    const n = parseFloat(draft);
    return isNaN(n) ? { ok: false, value: null } : { ok: true, value: n };
  }
  if (vt === 'str' || vt === 'string') return { ok: true, value: draft };
  if (vt === 'vector' || vt === 'list' || vt === 'array') {
    try {
      const arr = JSON.parse(draft);
      return Array.isArray(arr) ? { ok: true, value: arr } : { ok: false, value: null };
    } catch {
      return { ok: false, value: null };
    }
  }
  // 'any' — try JSON, fall back to raw string
  try { return { ok: true, value: JSON.parse(draft) }; }
  catch { return { ok: true, value: draft }; }
}

function InlinePortEditor({
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

  // Sync from external refresh (e.g. execution) when not focused
  useEffect(() => {
    if (!focused) {
      setDraft(valueToEditString(port.valueType, port.value));
      setHasError(false);
    }
  }, [port.value, port.valueType, focused]);

  if (vt === 'bool') {
    const checked = port.value === true || port.value === 1 || port.value === 'true';
    return (
      <Checkbox
        mt={4}
        ml={16}
        size="xs"
        color="teal"
        label="Enabled"
        className="property-inspector-control"
        checked={checked}
        onChange={(e) => onCommit(port.name, e.target.checked)}
      />
    );
  }

  const commit = () => {
    const { ok, value } = parsePortInput(port.valueType, String(draft));
    if (ok) {
      setHasError(false);
      onCommit(port.name, value);
    } else {
      setHasError(true);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      commit();
      (event.target as HTMLElement).blur();
    }
    if (event.key === 'Escape') {
      setDraft(valueToEditString(port.valueType, port.value));
      setHasError(false);
      (event.target as HTMLElement).blur();
    }
  };

  const isNumeric = vt === 'int' || vt === 'float' || vt === 'number';
  const isLongForm = vt === 'vector' || vt === 'list' || vt === 'array' || vt === 'any';
  const commonProps = {
    value: draft,
    error: hasError ? 'Invalid value' : undefined,
    onFocus: () => setFocused(true),
    onBlur: () => { setFocused(false); commit(); },
    className: 'property-inspector-control',
  };

  if (isNumeric) {
    return (
      <NumberInput
        {...commonProps}
        mt={4}
        size="xs"
        step={vt === 'int' ? 1 : 0.1}
        allowDecimal={vt !== 'int'}
        hideControls
        placeholder={vt === 'int' ? '0' : '0.0'}
        onChange={(value) => { setDraft(String(value ?? '')); setHasError(false); }}
        onKeyDown={handleKeyDown}
      />
    );
  }

  if (isLongForm) {
    return (
      <Textarea
        {...commonProps}
        mt={4}
        size="xs"
        autosize
        minRows={1}
        maxRows={4}
        placeholder={vt === 'vector' ? '[1, 2, 3]' : 'JSON or text'}
        onChange={(e) => { setDraft(e.currentTarget.value); setHasError(false); }}
        onKeyDown={handleKeyDown}
      />
    );
  }

  return (
    <TextInput
      {...commonProps}
      mt={4}
      size="xs"
      placeholder="value"
      onChange={(e) => { setDraft(e.currentTarget.value); setHasError(false); }}
      onKeyDown={handleKeyDown}
    />
  );
}

// ── PortList ───────────────────────────────────────────────────────────────────

function PortList({
  ports,
  title,
  nodeId,
  onSetPortValue,
}: {
  ports: SerializedPort[];
  title: string;
  nodeId?: string;
  onSetPortValue?: (portName: string, value: any) => void;
}) {
  if (ports.length === 0) return null;

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center" px={2}>
        <Text size="10px" fw={800} tt="uppercase" lts="0.16em" c="dimmed">
          {title}
        </Text>
        <Badge variant="light" color="gray" size="xs" radius="xl">
          {ports.length}
        </Badge>
      </Group>
      {ports.map((p) => {
        const dotColor = PORT_COLORS[p.function] ?? '#9ea3c0';
        const typeColor = valueTypeColor(p.valueType);
        const displayValue = formatValue(p.value);
        const isEditable =
          nodeId &&
          onSetPortValue &&
          p.function === 'DATA' &&
          p.direction === 'INPUT' &&
          !p.connected;

        return (
          <Paper key={p.name} className="property-inspector-port" p="xs" radius="md" withBorder>
            <Group gap="xs" wrap="nowrap" align="center">
              <Box style={portDotStyle(dotColor)} />
              <Text size="xs" fw={600} c="var(--foreground)" truncate style={{ flex: 1 }} title={p.name}>
                {p.name}
              </Text>
              <Badge
                variant="outline"
                radius="sm"
                size="xs"
                ff="var(--font-mono)"
                style={{ borderColor: typeColor, color: typeColor }}
              >
                {p.valueType}
              </Badge>
            </Group>
            {isEditable ? (
              <InlinePortEditor port={p} onCommit={onSetPortValue!} />
            ) : (
              displayValue !== null && (
                <Code block mt={6} className="property-inspector-value" title={String(displayValue)}>
                  {displayValue}
                </Code>
              )
            )}
          </Paper>
        );
      })}
    </Stack>
  );
}

function formatValue(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// ── NodeIdRow ─────────────────────────────────────────────────────────────────

function NodeIdRow({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [id]);

  return (
    <Group gap="xs" wrap="nowrap" align="start">
      <Code block className="property-inspector-id">
        {id}
      </Code>
      <Tooltip label={copied ? 'Copied' : 'Copy node id'} withArrow>
        <ActionIcon
          size="sm"
          variant="subtle"
          color={copied ? 'green' : 'gray'}
          onClick={copy}
          aria-label="Copy node id"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

// ── HumanInputForm ──────────────────────────────────────────────────────────

function HumanInputForm({
  nodeId, prompt, runId, networkId,
}: { nodeId: string; prompt: string; runId: string | null; networkId: string | null }) {
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!response.trim() || !runId || !networkId) return;
    setSubmitting(true);
    try {
      await graphClient.submitHumanInput(runId, networkId, nodeId, response.trim());
      setResponse('');
    } catch { /* stay waiting */ } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Divider className="property-inspector-divider" />
      <Paper className="property-inspector-callout property-inspector-callout--human" p="sm" radius="md" withBorder>
        <Stack gap="xs">
          <Text size="10px" ff="var(--font-mono)" lts="0.16em" tt="uppercase" c="violet.3">
            Awaiting Input
          </Text>
          <Text size="xs" c="dimmed" lh={1.5}>{prompt}</Text>
          <Textarea
            minRows={3}
            autosize
            maxRows={5}
            size="xs"
            className="property-inspector-control"
            value={response}
            placeholder="Type your response..."
            onChange={(e) => setResponse(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); }
            }}
          />
          <Group justify="space-between" align="center">
            <Text size="10px" c="dimmed">
              <Kbd size="xs">cmd</Kbd> + <Kbd size="xs">enter</Kbd>
            </Text>
            <Button
              size="compact-xs"
              color="violet"
              variant={response.trim() && !submitting ? 'filled' : 'outline'}
              onClick={submit}
              disabled={submitting || !response.trim()}
            >
              {submitting ? 'Submitting...' : 'Submit'}
            </Button>
          </Group>
        </Stack>
      </Paper>
    </>
  );
}

// ── ParameterPane ──────────────────────────────────────────────────────────────

function ParameterPaneComponent({
  selected,
  onSetPortValue,
}: {
  selected: SelectedNodeInfo | null;
  onSetPortValue?: (nodeId: string, portName: string, value: any) => void;
}) {
  const traceInfo = useTraceStore(s => selected ? s.nodeStates[selected.id] : undefined);

  return (
    <aside className="property-inspector panel">
      <Box className="property-inspector-header">
        <Text size="10px" fw={800} tt="uppercase" lts="0.18em" c="dimmed">
          Property Inspector
        </Text>
        <Text size="xs" c="teal.2" fw={700}>
          Node details
        </Text>
      </Box>

      {!selected ? (
        <Center className="property-inspector-empty">
          <Stack gap={6} align="center">
            <Text size="sm" fw={700} c="var(--foreground)">No node selected</Text>
            <Text size="xs" c="dimmed" ta="center" maw={180}>
              Select a node on the canvas to inspect and edit its disconnected inputs.
            </Text>
          </Stack>
        </Center>
      ) : (
        <ScrollArea className="property-inspector-scroll" scrollbarSize={6}>
          <Stack gap="sm" p="sm">
            {/* Node identity */}
            <Paper className="property-inspector-card property-inspector-card--hero" p="sm" radius="lg" withBorder>
              <Stack gap="xs">
                <Text size="sm" fw={700} c="var(--foreground)" truncate title={selected.label}>
                  {selected.label}
                </Text>
                <Group gap={6}>
                  <Badge
                    variant="light"
                    color={selected.flowType === 'networkNode' ? 'violet' : 'teal'}
                    radius="xl"
                    size="sm"
                  >
                    {selected.flowType === 'networkNode' ? 'Network' : 'Function'}
                  </Badge>
                  {selected.isFlowControlNode && (
                    <Badge variant="light" color="pink" radius="xl" size="sm">Control</Badge>
                  )}
                  {selected.subnetworkId && (
                    <Badge variant="light" color="green" radius="xl" size="sm">Subgraph</Badge>
                  )}
                </Group>
              </Stack>
            </Paper>

            {/* Ports */}
            <PortList
              ports={selected.inputs}
              title="Inputs"
              nodeId={selected.id}
              onSetPortValue={
                onSetPortValue
                  ? (pn, v) => onSetPortValue(selected.id, pn, v)
                  : undefined
              }
            />

            {selected.inputs.length > 0 && selected.outputs.length > 0 && (
              <Divider className="property-inspector-divider" />
            )}
            <PortList ports={selected.outputs} title="Outputs" />

            {/* Live trace panels */}
            {traceInfo?.streamBuffer !== undefined && (
              <>
                <Divider className="property-inspector-divider" />
                <Paper className="property-inspector-callout property-inspector-callout--stream" p="sm" radius="md" withBorder>
                  <Stack gap={6}>
                    <Text size="10px" ff="var(--font-mono)" lts="0.16em" tt="uppercase" c="yellow.5">
                      Streaming
                    </Text>
                    <Box component="pre" className="property-inspector-pre">
                      {traceInfo.streamBuffer || '...'}
                    </Box>
                  </Stack>
                </Paper>
              </>
            )}

            {traceInfo?.agentSteps && traceInfo.agentSteps.length > 0 && (
              <>
                <Divider className="property-inspector-divider" />
                <Stack gap="xs">
                  <Text size="10px" fw={800} tt="uppercase" lts="0.16em" c="dimmed">
                    Agent Steps
                  </Text>
                  {traceInfo.agentSteps.map(step => (
                    <Paper key={step.step} className="property-inspector-callout property-inspector-callout--step" p="xs" radius="md" withBorder>
                      <Text size="10px" c="yellow.5" mb={3}>
                        Step {step.step} <Text span c="violet.3">{step.tool}</Text>
                      </Text>
                      <Text size="10px" c="dimmed">in: <Text span c="blue.1">{step.input}</Text></Text>
                      <Text size="10px" c="dimmed" mt={2}>out: <Text span c="green.3">{step.output}</Text></Text>
                    </Paper>
                  ))}
                </Stack>
              </>
            )}

            {traceInfo?.detail && Object.keys(traceInfo.detail).length > 0 && (
              <>
                <Divider className="property-inspector-divider" />
                <Group gap={6}>
                  {Object.entries(traceInfo.detail).map(([k, v]) => (
                    <Badge key={k} variant="light" color="yellow" radius="sm" ff="var(--font-mono)">
                      {k}: {String(v)}
                    </Badge>
                  ))}
                </Group>
              </>
            )}

            <Divider className="property-inspector-divider" />
            <Paper className="property-inspector-card" p="sm" radius="md" withBorder>
              <Text size="10px" c="dimmed" mb={6} tt="uppercase" lts="0.16em" fw={800}>
                Node ID
              </Text>
              <NodeIdRow id={selected.id} />
            </Paper>

            {/* Human-in-the-loop input */}
            {(traceInfo as any)?.humanInputWaiting && (
              <HumanInputForm
                nodeId={selected.id}
                prompt={(traceInfo as any).humanInputWaiting.prompt}
                runId={(traceInfo as any).humanInputWaiting.runId}
                networkId={(traceInfo as any).humanInputWaiting.networkId}
              />
            )}
          </Stack>
        </ScrollArea>
      )}
    </aside>
  );
}

export const ParameterPane = React.memo(ParameterPaneComponent);
