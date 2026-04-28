/**
 * NodePalette — left-side panel for browsing and adding nodes.
 *
 * Features:
 * - Live search / filter
 * - Categorised sections (auto-derived from type name conventions)
 * - Click to add at canvas centre
 * - Drag onto the canvas to place at a specific position
 * - Subnetwork section with name input
 */
import React, { useMemo, useState } from 'react';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Collapse,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import { useGraphStore } from '../../store/graphStore';
import { getNodeIcon } from '../../lib/nodeIcons';
import { HugeiconsIcon } from '@hugeicons/react';
import { Add01Icon, ArrowRight01Icon } from '@hugeicons/core-free-icons';

// ── Category definitions ──────────────────────────────────────────────────────

const CATEGORY_ORDER = ['Math', 'Flow', 'Data', 'Agent', 'Imaging', 'Other'];

const CATEGORY_COLORS: Record<string, string> = {
  Math:    '#60a5fa',
  Flow:    '#f472b6',
  Data:    '#5eead4',
  Agent:   '#fbbf24',
  Imaging: '#c084fc',
  Other:   '#94a3b8',
};

const CATEGORY_FOR_TYPE: Record<string, string> = {
  // Core
  ConstantNode:        'Data',
  AddNode:             'Math',
  MultiplyNode:        'Math',
  PrintNode:           'Flow',
  BranchNode:          'Flow',

  // LLM / language
  PromptTemplateNode:  'Data',
  LLMNode:             'Agent',
  LLMStreamNode:       'Agent',
  ToolAgentNode:       'Agent',
  ToolAgentStreamNode: 'Agent',
  EmbeddingNode:       'Data',
  TextSplitterNode:    'Data',

  // Vision / image
  ImageGenNode:        'Agent',
  ImageGenExecNode:    'Agent',
  GPT4VisionNode:      'Agent',
  PromptRefinerNode:   'Agent',
  PromptRefineExecNode:'Agent',

  // Control flow (extended)
  WhileLoopNode:       'Flow',

  // Privacy
  AnonymizerNode:      'Data',
  SummarizerNode:      'Data',

  // pydantic-ai powered agent nodes
  PydanticAgentNode:   'Agent',
  LLMCallNode:         'Agent',
  AgentPlannerNode:    'Agent',

  // Human-in-the-loop
  HumanInputNode:      'Agent',

  // Imaging / diffusion (ComfyUI-style)
  CheckpointLoader:    'Imaging',
  CLIPTextEncode:      'Imaging',
  EmptyLatentImage:    'Imaging',
  KSampler:            'Imaging',
  KSamplerStep:        'Imaging',
  TiledKSampler:       'Imaging',
  VAEDecode:           'Imaging',
  VAEEncode:           'Imaging',
  LoadImage:           'Imaging',
  SaveImage:           'Imaging',
};

function categorize(type: string): string {
  return CATEGORY_FOR_TYPE[type] ?? 'Other';
}

// ── PaletteItem ───────────────────────────────────────────────────────────────

function PaletteItem({
  type,
  color,
  onAdd,
}: {
  type: string;
  color: string;
  onAdd: (type: string) => void;
}) {
  const NodeIcon = getNodeIcon(type);

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('application/nodegraph-type', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <Paper
      className="node-palette-item"
      p={6}
      radius="md"
      withBorder
      draggable
      onDragStart={handleDragStart}
      title={`Drag to canvas or click + to add ${type}`}
    >
      <Group gap="xs" wrap="nowrap">
        <ThemeIcon
          className="node-palette-item-icon"
          variant="light"
          size="sm"
          radius="md"
          style={{ '--node-palette-accent': color } as React.CSSProperties}
        >
          <NodeIcon size={14} color={color} strokeWidth={2} />
        </ThemeIcon>
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Text size="xs" fw={650} c="var(--foreground)" truncate>
            {type.replace('Node', '')}
          </Text>
          <Text size="9px" c="dimmed" truncate ff="var(--font-mono)">
            {type}
          </Text>
        </Box>
        <Tooltip label={`Add ${type}`} withArrow>
          <ActionIcon
            className="node-palette-add"
            size="sm"
            variant="subtle"
            aria-label={`Add ${type}`}
            style={{ color }}
            onClick={(e) => { e.stopPropagation(); onAdd(type); }}
          >
            <HugeiconsIcon icon={Add01Icon} className="!size-3.5" />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Paper>
  );
}

// ── CategorySection ───────────────────────────────────────────────────────────

function CategorySection({
  name,
  types,
  color,
  onAdd,
}: {
  name: string;
  types: string[];
  color: string;
  onAdd: (type: string) => void;
}) {
  const [open, setOpen] = useState(true);

  if (types.length === 0) return null;

  return (
    <Paper className="node-palette-section" p="xs" radius="lg" withBorder>
      <UnstyledButton
        className="node-palette-section-header"
        onClick={() => setOpen((o) => !o)}
      >
        <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
          <Box className="node-palette-dot" style={{ background: color }} />
          <Text size="10px" fw={800} c="dimmed" tt="uppercase" lts="0.16em" truncate>
            {name}
          </Text>
        </Group>
        <Badge variant="light" color="gray" size="xs" radius="xl">
          {types.length}
        </Badge>
        <HugeiconsIcon
          icon={ArrowRight01Icon}
          className="node-palette-section-chevron"
          style={{ transform: open ? 'rotate(90deg)' : undefined }}
        />
      </UnstyledButton>
      <Collapse expanded={open}>
        <Stack gap={6} mt="xs">
          {types.map((type) => (
            <PaletteItem key={type} type={type} color={color} onAdd={onAdd} />
          ))}
        </Stack>
      </Collapse>
    </Paper>
  );
}

// ── NodePalette ───────────────────────────────────────────────────────────────

function NodePaletteComponent({
  onAddNode,
  onAddSubnetwork,
}: {
  onAddNode: (type: string) => void;
  onAddSubnetwork: (name: string) => void;
}) {
  const nodeTypes = useGraphStore((s) => s.nodeTypes);
  const [search, setSearch] = useState('');
  const [subnetName, setSubnetName] = useState('');

  // Build categorised groups, filtered by search
  const groups = useMemo(() => {
    const q = search.toLowerCase();
    const filtered = nodeTypes.filter((t) => t.toLowerCase().includes(q));

    const map: Record<string, string[]> = {};
    for (const cat of CATEGORY_ORDER) map[cat] = [];
    for (const type of filtered) {
      const cat = categorize(type);
      if (!map[cat]) map[cat] = [];
      map[cat].push(type);
    }
    return map;
  }, [nodeTypes, search]);

  const handleSubnetAdd = () => {
    const name = subnetName.trim() || `Subnet_${Date.now()}`;
    onAddSubnetwork(name);
    setSubnetName('');
  };

  return (
    <aside className="node-palette panel">
      {/* Header + search */}
      <Box className="node-palette-header">
        <Group justify="space-between" align="start" mb="xs">
          <Box>
            <Text size="10px" fw={800} tt="uppercase" lts="0.18em" c="dimmed">
              Node Palette
            </Text>
            <Text size="xs" c="teal.2" fw={700}>
              Add building blocks
            </Text>
          </Box>
          <Badge variant="light" color="teal" radius="xl" size="sm">
            {nodeTypes.length}
          </Badge>
        </Group>
        <TextInput
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          spellCheck={false}
          size="xs"
          className="node-palette-control"
        />
      </Box>

      {/* Hint */}
      <Group className="node-palette-hint" gap={6} wrap="nowrap">
        <Box className="node-palette-hint-dot" />
        <Text size="10px" c="dimmed">Click add or drag cards onto the canvas</Text>
      </Group>

      {/* Categorised node list */}
      <ScrollArea className="node-palette-scroll" scrollbarSize={6}>
        <Stack gap="xs" p="sm">
          {CATEGORY_ORDER.map((cat) => (
            <CategorySection
              key={cat}
              name={cat}
              types={groups[cat] ?? []}
              color={CATEGORY_COLORS[cat]}
              onAdd={onAddNode}
            />
          ))}
        </Stack>
      </ScrollArea>

      {/* Subnetwork creator */}
      <Box className="node-palette-footer">
        <Paper className="node-palette-subnet" p="sm" radius="lg" withBorder>
          <Stack gap="xs">
            <Group gap="xs" wrap="nowrap">
              <Box className="node-palette-subnet-icon" />
              <Text size="10px" fw={800} c="teal.2" tt="uppercase" lts="0.16em">
                Subnetwork
              </Text>
            </Group>
            <TextInput
              placeholder="Name..."
              value={subnetName}
              onChange={(e) => setSubnetName(e.currentTarget.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubnetAdd()}
              spellCheck={false}
              size="xs"
              className="node-palette-control"
            />
            <Button
              variant="light"
              color="teal"
              size="compact-sm"
              fullWidth
              leftSection={<HugeiconsIcon icon={Add01Icon} className="!size-3.5" />}
              onClick={handleSubnetAdd}
            >
              Add Subnetwork
            </Button>
          </Stack>
        </Paper>
      </Box>
    </aside>
  );
}

export const NodePalette = React.memo(NodePaletteComponent);
