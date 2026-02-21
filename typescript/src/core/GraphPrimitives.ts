import { v4 as uuidv4 } from 'uuid';
import { IGraphNode, INodePort, INode } from './Interface';

// ─────────────────────────────────────────────
// Edge — immutable connection record (mirrors Python NamedTuple)
// ─────────────────────────────────────────────

export class Edge {
  readonly from_node_id: string;
  readonly from_port_name: string;
  readonly to_node_id: string;
  readonly to_port_name: string;
  readonly edge_type: string;

  constructor(
    fromNodeId: string,
    fromPortName: string,
    toNodeId: string,
    toPortName: string,
    edgeType: string = 'default',
  ) {
    this.from_node_id = fromNodeId;
    this.from_port_name = fromPortName;
    this.to_node_id = toNodeId;
    this.to_port_name = toPortName;
    this.edge_type = edgeType;
  }

  toString(): string {
    return `Edge(${this.from_node_id}.${this.from_port_name} -> ${this.to_node_id}.${this.to_port_name})`;
  }
}

// ─────────────────────────────────────────────
// GraphNode — base class for graph nodes
// ─────────────────────────────────────────────

export class GraphNode extends IGraphNode {
  name: string;
  id: string;
  uuid: string;
  network_id: string | null;

  constructor(name: string, type: string, networkId: string | null = null) {
    super();
    this.name = name;
    this.id = uuidv4().replace(/-/g, '');
    this.uuid = uuidv4().replace(/-/g, '');
    this.network_id = networkId;
  }

  isNetwork(): boolean {
    return false;
  }

  toString(): string {
    return `GraphNode(${this.id})`;
  }
}

// Helper to make a Map key from a (nodeId, portName) tuple
function portKey(nodeId: string, portName: string): string {
  return `${nodeId}::${portName}`;
}

// ─────────────────────────────────────────────
// Graph — arena-pattern graph container
// ─────────────────────────────────────────────

export class Graph {
  nodes: Map<string, IGraphNode>;
  edges: Edge[];
  /** keyed by portKey(to_node_id, to_port_name) */
  private incoming_edges: Map<string, Edge[]>;
  /** keyed by portKey(from_node_id, from_port_name) */
  private outgoing_edges: Map<string, Edge[]>;

  constructor() {
    this.nodes = new Map();
    this.edges = [];
    this.incoming_edges = new Map();
    this.outgoing_edges = new Map();
  }

  /** Find a node in the graph by id */
  find_node_by_id(uid: string): IGraphNode | null {
    return this.nodes.get(uid) ?? null;
  }

  add_edge(
    fromNodeId: string,
    fromPortName: string,
    toNodeId: string,
    toPortName: string,
  ): Edge {
    const edge = new Edge(fromNodeId, fromPortName, toNodeId, toPortName);
    this.edges.push(edge);

    // incoming_edges indexed by destination
    const inKey = portKey(toNodeId, toPortName);
    if (!this.incoming_edges.has(inKey)) this.incoming_edges.set(inKey, []);
    this.incoming_edges.get(inKey)!.push(edge);

    // outgoing_edges indexed by source
    const outKey = portKey(fromNodeId, fromPortName);
    if (!this.outgoing_edges.has(outKey)) this.outgoing_edges.set(outKey, []);
    this.outgoing_edges.get(outKey)!.push(edge);

    // Mirror Python assertion: incoming edges for the FROM port should be < 2
    const fromInKey = portKey(fromNodeId, fromPortName);
    const fromIncoming = this.incoming_edges.get(fromInKey) ?? [];
    console.assert(
      fromIncoming.length < 2,
      'Incoming edge has more than 1 edge',
    );

    return edge;
  }

  get_incoming_edges(nodeId: string, portName: string): Edge[] {
    return this.incoming_edges.get(portKey(nodeId, portName)) ?? [];
  }

  get_outgoing_edges(nodeId: string, portName: string): Edge[] {
    return this.outgoing_edges.get(portKey(nodeId, portName)) ?? [];
  }

  add_node(node: IGraphNode): void {
    if (this.nodes.has(node.id)) {
      throw new Error(`Node with id '${node.name}' already exists in the network`);
    }
    console.log(`### Graph: Adding node ${node.name} to global registry`, node.network_id);
    this.nodes.set(node.id, node);
  }

  /** Alias: mirrors Python Graph.get_node_by_id */
  get_node_by_id(nodeId: string): IGraphNode | null {
    return this.nodes.get(nodeId) ?? null;
  }

  /** Alias: mirrors Python Graph.getNode */
  getNode(nodeId: string): IGraphNode | null {
    return this.get_node_by_id(nodeId);
  }

  get_node_by_name(name: string): IGraphNode | null {
    for (const node of this.nodes.values()) {
      if (node.name === name) return node;
    }
    return null;
  }

  get_node_by_path(path: string): IGraphNode | null {
    for (const node of this.nodes.values()) {
      if (this.get_path(node.id) === path) return node;
    }
    return null;
  }

  getNetwork(networkId: string | null): IGraphNode | null {
    if (!networkId) return null;
    const network = this.get_node_by_id(networkId);
    if (!network) return null;
    if (!network.isNetwork()) {
      throw new Error(`Node with ID '${networkId}' is not a Network`);
    }
    return network;
  }

  get_path(nodeId: string): string {
    const node = this.get_node_by_id(nodeId);
    if (!node) throw new Error(`Node with ID '${nodeId}' not found`);

    const pathElements: string[] = [];
    let curParent = this.getNetwork(node.network_id);
    while (curParent) {
      pathElements.push(curParent.name);
      curParent = this.getNetwork(curParent.network_id);
    }

    pathElements.reverse();
    let fullPath = '/' + pathElements.join('/');
    if (node.isNetwork()) {
      fullPath += `/${node.name}`;
    } else {
      fullPath += `:${node.name}`;
    }

    // Fix double-slash at root
    if (fullPath.startsWith('//')) {
      fullPath = fullPath.slice(1);
    }
    return fullPath;
  }

  deleteNode(nodeId: string): void {
    const node = this.get_node_by_id(nodeId);
    if (!node) {
      throw new Error(`Node with id '${nodeId}' does not exist in the network`);
    }

    const id = node.id;

    // Arena Pattern: Cleanup connections associated with this node
    this.edges = this.edges.filter(
      (e) => e.from_node_id !== id && e.to_node_id !== id,
    );

    // Rebuild incoming/outgoing maps after deletion
    this._rebuildEdgeMaps();

    this.nodes.delete(id);
  }

  private _rebuildEdgeMaps(): void {
    this.incoming_edges.clear();
    this.outgoing_edges.clear();
    for (const edge of this.edges) {
      const inKey = portKey(edge.to_node_id, edge.to_port_name);
      if (!this.incoming_edges.has(inKey)) this.incoming_edges.set(inKey, []);
      this.incoming_edges.get(inKey)!.push(edge);

      const outKey = portKey(edge.from_node_id, edge.from_port_name);
      if (!this.outgoing_edges.has(outKey)) this.outgoing_edges.set(outKey, []);
      this.outgoing_edges.get(outKey)!.push(edge);
    }
  }

  reset(): void {
    this.nodes.clear();
    this.edges = [];
    this.incoming_edges.clear();
    this.outgoing_edges.clear();
  }

  get_downstream_ports(srcPort: INodePort, includeIoPorts: boolean = false): INodePort[] {
    const downstreamPorts: INodePort[] = [];
    const outgoingEdges = this.get_outgoing_edges((srcPort as any).node_id, (srcPort as any).port_name);

    for (const edge of outgoingEdges) {
      const destNode = this.get_node_by_id(edge.to_node_id) as any;
      if (!destNode) continue;

      let destPort: INodePort | null = destNode.inputs?.[edge.to_port_name] ?? null;
      if (!destPort) destPort = destNode.outputs?.[edge.to_port_name] ?? null;
      if (!destPort) continue;

      if ((destPort as any).isInputOutputPort()) {
        if (includeIoPorts) downstreamPorts.push(destPort as INodePort);
        downstreamPorts.push(
          ...this.get_downstream_ports(destPort as INodePort, includeIoPorts),
        );
      } else {
        downstreamPorts.push(destPort as INodePort);
      }
    }

    return downstreamPorts;
  }

  get_upstream_ports(port: INodePort, includeIoPorts: boolean = false): INodePort[] {
    const upstreamPorts: INodePort[] = [];
    const incomingEdges = this.get_incoming_edges((port as any).node_id, (port as any).port_name);

    for (const edge of incomingEdges) {
      const srcNode = this.get_node_by_id(edge.from_node_id) as any;
      if (!srcNode) continue;

      let srcPort: INodePort | null = srcNode.outputs?.[edge.from_port_name] ?? null;
      if (!srcPort) srcPort = srcNode.inputs?.[edge.from_port_name] ?? null;
      if (!srcPort) continue;

      if ((srcPort as any).isInputOutputPort()) {
        if (includeIoPorts) upstreamPorts.push(srcPort as INodePort);
        upstreamPorts.push(...this.get_upstream_ports(srcPort as INodePort));
      } else {
        upstreamPorts.push(srcPort as INodePort);
      }
    }

    return upstreamPorts;
  }

  get_upstream_nodes(port: INodePort): IGraphNode[] {
    const upstreamNodes: IGraphNode[] = [];
    const incomingEdges = this.get_incoming_edges(
      (port as any).node_id,
      (port as any).port_name,
    );
    for (const edge of incomingEdges) {
      const srcNode = this.get_node_by_id(edge.from_node_id);
      if (srcNode && !upstreamNodes.includes(srcNode)) {
        upstreamNodes.push(srcNode);
      }
    }
    return upstreamNodes;
  }

  get_downstream_nodes(port: INodePort): IGraphNode[] {
    const downstreamNodes: IGraphNode[] = [];
    const outgoingEdges = this.get_outgoing_edges(
      (port as any).node_id,
      (port as any).port_name,
    );
    for (const edge of outgoingEdges) {
      const destNode = this.get_node_by_id(edge.to_node_id);
      if (destNode && !downstreamNodes.includes(destNode)) {
        downstreamNodes.push(destNode);
      }
    }
    return downstreamNodes;
  }
}
