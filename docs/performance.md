# Drag & Canvas Performance

Reference: https://reactflow.dev/learn/advanced-use/performance

---

## Fixed

### 1. `backdrop-filter: blur(18px)` suppressed during node drags — CRITICAL
**Files:** `globals.css`, `GraphCanvas.tsx`

Both `.node-palette` and `.property-inspector` had `backdrop-filter: blur(18px)` applied
unconditionally. During a drag the GPU must re-sample and re-blur the entire canvas region
behind both panels on every `pointermove` frame, even though the panels themselves don't move.

**Fix:** A `.dragging-nodes` class is added to the outermost canvas container in `GraphCanvas.tsx`
while `isDraggingNodes` is `true`. A CSS rule in `globals.css` overrides `backdrop-filter: none`
on both sidebars for the duration of the drag:

```css
.dragging-nodes .node-palette,
.dragging-nodes .property-inspector {
  backdrop-filter: none;
}
```

The `isDraggingNodes` state is already tracked via `onNodeDragStart` / `onNodeDragStop` and
`onSelectionDragStart` / `onSelectionDragStop`. No additional state was needed.

---

### 2. Semi-transparent node card backgrounds made fully opaque — HIGH
**File:** `globals.css`

`--node-card-bg` and `--node-card-header` were partially transparent, forcing the browser to
composite every node card as an independent blending layer on every paint. With many nodes
dragging across the dot-grid background this multiplied paint cost linearly with node count.

**Fix:**

| Variable | Before | After |
|---|---|---|
| `--node-card-bg` (dark) | `rgba(15, 23, 42, 0.9)` | `rgb(15, 23, 42)` |
| `--node-card-header` (dark) | `rgba(15, 23, 42, 0.68)` | `rgb(11, 18, 36)` |
| `--node-card-bg` (light) | `color-mix(in srgb, var(--card) 94%, transparent)` | `var(--card)` |
| `--node-card-header` (light) | `color-mix(in srgb, var(--sidebar) 88%, transparent)` | `var(--sidebar)` |

The border variables remain semi-transparent — thin borders have negligible compositing cost.

---

### 3. `transform` removed from `.node-card` CSS transition — HIGH
**File:** `globals.css`

Including `transform` in a `transition` declaration causes browsers to implicitly promote the
element to a GPU compositor layer (`will-change: transform` semantics). With dozens of nodes on
screen, this created dozens of compositor layers. The GPU memory bandwidth and compositing
overhead of tearing down and rebuilding all those layers on each drag frame outweighed the
original CPU paint savings.

**Fix:** `transform` was removed from the `.node-card` transition list:

```css
/* before */
transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;

/* after */
transition: border-color 160ms ease, box-shadow 160ms ease;
```

---

## Todo (Medium Priority)

### 4. Memoize `InputRow` and `OutputRow` sub-components
**Files:** `FunctionNode.tsx`, `NetworkNode.tsx`

`FunctionNode` and `NetworkNode` are wrapped in `React.memo` with a custom comparator that
includes `prev.dragging === next.dragging`. When a drag starts or stops this triggers a
re-render, which cascades through all `InputRow` and `OutputRow` children since they are plain
(un-memoized) inner functions. A node with 8 inputs + 8 outputs re-renders 16 rows twice per
drag event.

**Suggested fix:** Wrap both with `React.memo`. Also requires extracting the inline
`onSetPortValue` arrow function into a `useCallback` (see item #5) or the memo will always bail
out due to a new function reference.

---

### 5. Memoize `onSetPortValue` and `onRename` callbacks in `FunctionNodeComponent`
**File:** `FunctionNode.tsx`

These are currently created as new arrow functions on every render:

```tsx
// Each render creates new function references — breaks child memo
onSetPortValue={(portName, value) => setPortValue(id, portName, value)}
onRename={(name) => renameNode(id, name)}
```

**Suggested fix:**

```tsx
const handleSetPortValue = useCallback(
  (portName: string, value: unknown) => setPortValue(id, portName, value),
  [id, setPortValue],
);
const handleRename = useCallback(
  (name: string) => renameNode(id, name),
  [id, renameNode],
);
```

This is a prerequisite for item #4 to have effect on `InputRow`.

---

### 6. Pre-compute `nodeCardStyle` / `nodeAccentRailStyle` as module-level constants
**File:** `FunctionNode.tsx`, `NetworkNode.tsx`, `nodeVisuals.tsx`

`nodeCardStyle(accent)` and `nodeAccentRailStyle(accent, state)` return new object literals on
every call. Since `DATA_COL` / `NET_COL` are module-level constants, the per-variant results
never change and can be computed once:

```ts
// In FunctionNode.tsx — computed once at module load
const FUNCTION_CARD_STYLE = nodeCardStyle(DATA_COL);
const ACCENT_RAIL_STYLES = {
  idle:     nodeAccentRailStyle(DATA_COL, 'idle'),
  selected: nodeAccentRailStyle(DATA_COL, 'selected'),
  running:  nodeAccentRailStyle(DATA_COL, 'running'),
  // ...
} as const;
```

This eliminates allocations inside render hot paths.

---

### 7. Simplify box-shadow in `node-card--selected` and `node-card--running`
**File:** `globals.css`

`color-mix()` inside `box-shadow` is resolved at paint time. The animated `node-card--running`
keyframes change the shadow values at 60 fps, and the `node-card--selected` shadow uses
`color-mix` per-paint. During drag, any selected node incurs this cost on every frame.

**Suggested fix:** Pre-compute the `color-mix` to a static RGBA value at design time:

```css
/* before */
.node-card--selected {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--node-accent) 36%, transparent), var(--node-card-shadow);
}

/* after — accent at 36% against transparent ≈ rgba(accent, 0.36); use the teal default */
.node-card--selected {
  box-shadow: 0 0 0 1px rgba(94, 234, 212, 0.36), var(--node-card-shadow);
}
```

---

### 8. `Date.now()` inside Zustand selector
**File:** `GraphCanvas.tsx`

```ts
const activeEdgeSerial = useTraceStore((s) => {
  const now = Date.now();  // called on every store update
  return s.activeEdges.filter((e) => e.expiresAt > now)...
```

Zustand re-runs selectors on every store state change to test for equality. `Date.now()` is a
no-op allocation issue but can produce incorrect memoization when `activeEdges` is unchanged but
time has advanced past an expiry. Consider moving expiry filtering to a dedicated selector or
store slice that updates on a timer instead of piggybacking on the main store subscription.
