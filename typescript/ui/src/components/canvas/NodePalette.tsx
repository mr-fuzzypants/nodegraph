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

// ── Category definitions ──────────────────────────────────────────────────────

const CATEGORY_ORDER = ['Math', 'Flow', 'Data', 'Other'];

const CATEGORY_COLORS: Record<string, string> = {
  Math:  '#6d7de8',
  Flow:  '#f38ba8',
  Data:  '#4ade80',
  Other: '#9ea3c0',
};

const CATEGORY_FOR_TYPE: Record<string, string> = {
  ConstantNode:  'Data',
  AddNode:       'Math',
  MultiplyNode:  'Math',
  PrintNode:     'Flow',
  BranchNode:    'Flow',
};

function categorize(type: string): string {
  return CATEGORY_FOR_TYPE[type] ?? 'Other';
}

// ── Styles ────────────────────────────────────────────────────────────────────

const S = {
  aside: {
    width: 200,
    background: '#13141f',
    borderRight: '1px solid #2c2f45',
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
    userSelect: 'none' as const,
    flexShrink: 0,
  },
  header: {
    padding: '10px 10px 6px',
    borderBottom: '1px solid #2c2f45',
    flexShrink: 0,
  },
  title: {
    color: '#a78bfa',
    fontFamily: 'monospace',
    fontWeight: 'bold' as const,
    fontSize: 12,
    letterSpacing: 0.5,
    marginBottom: 6,
    display: 'block',
  },
  searchInput: {
    width: '100%',
    background: '#11121c',
    border: '1px solid #2c2f45',
    borderRadius: 4,
    color: '#c9cce8',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: '4px 8px',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '6px 0',
  },
  section: {
    marginBottom: 4,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 10px',
    cursor: 'pointer',
    userSelect: 'none' as const,
  },
  sectionDot: (color: string): React.CSSProperties => ({
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: color,
    flexShrink: 0,
  }),
  sectionLabel: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: 'bold' as const,
    color: '#535677',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.8,
    flex: 1,
  },
  sectionChevron: (open: boolean): React.CSSProperties => ({
    color: '#535677',
    fontSize: 9,
    transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
    transition: 'transform 0.15s',
  }),
  item: (hovered: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '5px 10px 5px 22px',
    cursor: 'grab',
    background: hovered ? '#1e2133' : 'transparent',
    transition: 'background 0.1s',
  }),
  itemDot: (color: string): React.CSSProperties => ({
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: color,
    flexShrink: 0,
  }),
  itemLabel: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#c9cce8',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  addBtn: (color: string): React.CSSProperties => ({
    background: 'none',
    border: `1px solid ${color}`,
    borderRadius: 3,
    color: color,
    fontFamily: 'monospace',
    fontSize: 9,
    padding: '1px 4px',
    cursor: 'pointer',
    flexShrink: 0,
    lineHeight: 1.4,
  }),
  divider: {
    borderTop: '1px solid #2c2f45',
    margin: '6px 0',
  } as React.CSSProperties,
  subnetSection: {
    padding: '6px 10px 10px',
    borderTop: '1px solid #2c2f45',
    flexShrink: 0,
  },
  subnetLabel: {
    color: '#a78bfa',
    fontFamily: 'monospace',
    fontWeight: 'bold' as const,
    fontSize: 10,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.8,
    marginBottom: 6,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  subnetInput: {
    width: '100%',
    background: '#11121c',
    border: '1px solid #2c2f45',
    borderRadius: 4,
    color: '#c9cce8',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: '4px 8px',
    outline: 'none',
    boxSizing: 'border-box' as const,
    marginBottom: 6,
  },
  subnetBtn: {
    width: '100%',
    background: '#1e2133',
    border: '1px solid #a78bfa',
    borderRadius: 4,
    color: '#a78bfa',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: '5px 8px',
    cursor: 'pointer',
    textAlign: 'left' as const,
  },
};

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
  const [hovered, setHovered] = useState(false);

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('application/nodegraph-type', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div
      style={S.item(hovered)}
      draggable
      onDragStart={handleDragStart}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={`Drag to canvas or click + to add ${type}`}
    >
      <div style={S.itemDot(color)} />
      <span style={S.itemLabel}>{type.replace('Node', '')}</span>
      <button
        style={S.addBtn(color)}
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
    <div style={S.section}>
      <div style={S.sectionHeader} onClick={() => setOpen((o) => !o)}>
        <div style={S.sectionDot(color)} />
        <span style={S.sectionLabel}>{name}</span>
        <span style={S.sectionChevron(open)}>▶</span>
      </div>
      {open &&
        types.map((type) => (
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
    <aside style={S.aside}>
      {/* Header + search */}
      <div style={S.header}>
        <span style={S.title}>Node Palette</span>
        <input
          style={S.searchInput}
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          spellCheck={false}
        />
      </div>

      {/* Hint */}
      <div
        style={{
          padding: '4px 10px',
          color: '#535677',
          fontFamily: 'monospace',
          fontSize: 9,
          flexShrink: 0,
          borderBottom: '1px solid #1a1d2e',
        }}
      >
        Click + or drag to canvas
      </div>

      {/* Categorised node list */}
      <div style={S.scrollArea}>
        {CATEGORY_ORDER.map((cat) => (
          <CategorySection
            key={cat}
            name={cat}
            types={groups[cat] ?? []}
            color={CATEGORY_COLORS[cat]}
            onAdd={onAddNode}
          />
        ))}
      </div>

      {/* Subnetwork creator */}
      <div style={S.subnetSection}>
        <div style={S.subnetLabel}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              border: '1.5px solid #a78bfa',
              display: 'inline-block',
            }}
          />
          Subnetwork
        </div>
        <input
          style={S.subnetInput}
          placeholder="Name…"
          value={subnetName}
          onChange={(e) => setSubnetName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubnetAdd()}
          spellCheck={false}
        />
        <button style={S.subnetBtn} onClick={handleSubnetAdd}>
          ⊕ Add Subnetwork
        </button>
      </div>
    </aside>
  );
}
