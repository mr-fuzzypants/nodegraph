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
import { useGraphStore } from '../../store/graphStore';
import { getNodeIcon } from '../../lib/nodeIcons';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { cn } from '../../lib/utils';
import { HugeiconsIcon } from '@hugeicons/react';
import { Add01Icon, ArrowRight01Icon } from '@hugeicons/core-free-icons';

// ── Category definitions ──────────────────────────────────────────────────────

const CATEGORY_ORDER = ['Math', 'Flow', 'Data', 'Agent', 'Other'];

const CATEGORY_COLORS: Record<string, string> = {
  Math:  '#6d7de8',
  Flow:  '#f38ba8',
  Data:  '#4ade80',
  Agent: '#f59e0b',
  Other: '#9ea3c0',
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
    <div
      className="group flex items-center gap-2 px-2.5 py-1.5 cursor-grab hover:bg-accent rounded-sm mx-1 transition-colors"
      draggable
      onDragStart={handleDragStart}
      title={`Drag to canvas or click + to add ${type}`}
    >
      <NodeIcon size={13} color={color} strokeWidth={2} style={{ flexShrink: 0 }} />
      <span className="text-xs text-foreground flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-sans">
        {type.replace('Node', '')}
      </span>
      <button
        className="opacity-0 group-hover:opacity-100 text-[10px] px-1.5 py-0.5 rounded-sm border transition-opacity leading-tight"
        style={{ borderColor: color, color }}
        onClick={(e) => { e.stopPropagation(); onAdd(type); }}
        title={`Add ${type}`}
      >
        +
      </button>
    </div>
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
    <div className="mb-1">
      <button
        className="w-full flex items-center gap-1.5 px-2.5 py-1 cursor-pointer select-none hover:bg-accent rounded-sm mx-1 transition-colors"
        onClick={() => setOpen((o) => !o)}
        style={{ width: 'calc(100% - 8px)' }}
      >
        <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex-1 text-left font-sans">
          {name}
        </span>
        <HugeiconsIcon
          icon={ArrowRight01Icon}
          className={cn('!size-3 text-muted-foreground/50 transition-transform', open && 'rotate-90')}
        />
      </button>
      {open && types.map((type) => (
        <PaletteItem key={type} type={type} color={color} onAdd={onAdd} />
      ))}
    </div>
  );
}

// ── NodePalette ───────────────────────────────────────────────────────────────

export function NodePalette({
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
    <aside className="w-48 bg-background border-r border-border flex flex-col overflow-hidden shrink-0 select-none panel">
      {/* Header + search */}
      <div className="px-2.5 pt-2.5 pb-2 border-b border-border shrink-0">
        <span className="block text-xs font-bold text-primary tracking-wide mb-2 font-sans">
          Node Palette
        </span>
        <Input
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          spellCheck={false}
          className="h-6 text-xs"
        />
      </div>

      {/* Hint */}
      <div className="px-2.5 py-1 text-[10px] text-muted-foreground/60 shrink-0 border-b border-border font-sans">
        Click + or drag to canvas
      </div>

      {/* Categorised node list */}
      <ScrollArea className="flex-1 py-1.5">
        {CATEGORY_ORDER.map((cat) => (
          <CategorySection
            key={cat}
            name={cat}
            types={groups[cat] ?? []}
            color={CATEGORY_COLORS[cat]}
            onAdd={onAddNode}
          />
        ))}
      </ScrollArea>

      {/* Subnetwork creator */}
      <div className="px-2.5 py-2.5 border-t border-border shrink-0">
        <div className="flex items-center gap-1.5 mb-2">
          <div className="w-2 h-2 rounded-sm border-[1.5px]" style={{ borderColor: 'var(--primary)' }} />
          <span className="text-[10px] font-bold text-primary uppercase tracking-widest font-sans">
            Subnetwork
          </span>
        </div>
        <Input
          placeholder="Name…"
          value={subnetName}
          onChange={(e) => setSubnetName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubnetAdd()}
          spellCheck={false}
          className="h-6 text-xs mb-1.5"
        />
        <Button
          variant="outline"
          size="sm"
          className="w-full h-7 text-xs gap-1.5 border-primary text-primary hover:bg-primary/10"
          onClick={handleSubnetAdd}
        >
          <HugeiconsIcon icon={Add01Icon} className="!size-3" />
          Add Subnetwork
        </Button>
      </div>
    </aside>
  );
}
