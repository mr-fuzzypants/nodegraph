/** Shared UI-only types — deliberately separate from the server/core types. */

export interface SerializedPort {
  name: string;
  function: 'DATA' | 'CONTROL';
  direction: 'INPUT' | 'OUTPUT';
  valueType: string;
  value: any;
  /** True when an edge is wired into this input; unconnected inputs are editable. */
  connected?: boolean;
}

export interface SerializedNode {
  id: string;
  name: string;
  type: string;
  kind: 'FUNCTION' | 'NETWORK' | 'SELF';
  isFlowControlNode: boolean;
  path: string;
  inputs: SerializedPort[];
  outputs: SerializedPort[];
  subnetworkId?: string;
  position: { x: number; y: number };
}

export interface SerializedEdge {
  id: string;
  sourceNodeId: string;
  sourcePortName: string;
  targetNodeId: string;
  targetPortName: string;
}

export interface SerializedNetwork {
  id: string;
  name: string;
  path: string;
  parentId: string | null;
  nodes: SerializedNode[];
  edges: SerializedEdge[];
}

export interface NetworkListItem {
  id: string;
  name: string;
  path: string;
  parentId: string | null;
}

/** Data stored inside a ReactFlow node's `data` field.
 *  The index signature is required by @xyflow/react's `Record<string, unknown>` constraint.
 */
export interface NodeData extends Record<string, unknown> {
  label: string;
  /** Server-side node type string e.g. "ImageGenNode", "LLMNode" */
  nodeType: string;
  inputs: SerializedPort[];
  outputs: SerializedPort[];
  isFlowControlNode: boolean;
  /** Only set for NETWORK kind nodes */
  subnetworkId?: string;
  onEnter?: (subnetworkId: string) => void;
  /** Only set for SELF (tunnel proxy) nodes — allows the port editor to mutate tunnel ports */
  onAddTunnelPort?: (name: string, direction: 'input' | 'output') => Promise<void>;
  onRemoveTunnelPort?: (name: string, direction: 'input' | 'output') => Promise<void>;
}
