import { Node } from './Node';
import { Edge, Graph } from './GraphPrimitives';
import {
  InputOutputDataPort,
  InputOutputControlPort,
  NodePort,
  PortDirection,
  PortFunction,
  OutputControlPort,
} from './NodePort';
import { NodeKind } from './Types';
import { INodePort, INodeNetwork } from './Interface';
import {
  ExecCommand,
  ExecutionResult,
  ExecutionContext,
} from './Executor';

// ─────────────────────────────────────────────
// NodeNetwork
// ─────────────────────────────────────────────

export class NodeNetwork extends Node {
  // Separate registry for network types
  static _network_registry: Map<string, typeof NodeNetwork> = new Map();

  /** Decorator factory: mirrors Python @NodeNetwork.register */
  static register(typeName: string): (subclass: any) => any {
    return function (subclass: any): any {
      if (NodeNetwork._network_registry.has(typeName)) {
        throw new Error(`NodeNetwork type '${typeName}' is already registered.`);
      }
      NodeNetwork._network_registry.set(
        typeName,
        subclass as unknown as typeof NodeNetwork,
      );
      return subclass;
    };
  }

  static create_network(
    nodeName: string,
    typeName: string,
    networkId: string | null = null,
    graph: Graph | null = null,
  ): NodeNetwork {
    if (!NodeNetwork._network_registry.has(typeName)) {
      throw new Error(`Unknown node type '${typeName}'`);
    }
    const NodeClass = NodeNetwork._network_registry.get(typeName)!;
    const newNode = new (NodeClass as any)(nodeName, typeName, networkId, graph);

    if (newNode.graph) {
      newNode.graph.add_node(newNode);
    }

    console.log(
      `!!!!!!!!!!!!! Created NodeNetwork of type: ${typeName} with id: ${nodeName}`,
      newNode.id,
    );
    return newNode;
  }

  // ─── Instance state ───
  is_async_network: boolean;

  constructor(
    id: string,
    type: string,
    networkId: string | null = null,
    graph: Graph | null = null,
  ) {
    super(id, type, networkId);
    this.kind = NodeKind.NETWORK;
    this.graph = graph;
    this.network_id = networkId;
    this.is_flow_control_node = true;
    this.is_async_network = false;
    this.path = 'UNSet';
  }

  isRootNetwork(): boolean {
    return this.network_id === null;
  }

  isSubnetwork(): boolean {
    return this.network_id !== null;
  }

  isAsyncNetwork(): boolean {
    return false;
  }

  // ─── Port factory methods (tunneling ports) ───

  add_control_input_port(portName: string): InputOutputControlPort {
    if (portName in this.inputs) {
      throw new Error(
        `Control input port '${portName}' already exists in node '${this.id}'`,
      );
    }
    const port = new InputOutputControlPort(this.id, portName);
    this.inputs[portName] = port;
    return port;
  }

  add_data_input_port(portName: string): InputOutputDataPort {
    if (portName in this.inputs) {
      throw new Error(
        `Data input port '${portName}' already exists in node '${this.id}'`,
      );
    }
    const port = new InputOutputDataPort(this.id, portName);
    this.inputs[portName] = port;
    return port;
  }

  add_data_output_port(portName: string): InputOutputDataPort {
    if (portName in this.outputs) {
      throw new Error(
        `Data output port '${portName}' already exists in node '${this.id}'`,
      );
    }
    const port = new InputOutputDataPort(this.id, portName);
    this.outputs[portName] = port;
    return port;
  }

  remove_data_input_port(portName: string): void {
    if (!(portName in this.inputs)) {
      throw new Error(
        `Data input port '${portName}' does not exist in node '${this.id}'`,
      );
    }
    delete this.inputs[portName];
  }

  remove_data_output_port(portName: string): void {
    if (!(portName in this.outputs)) {
      throw new Error(
        `Data output port '${portName}' does not exist in node '${this.id}'`,
      );
    }
    delete this.outputs[portName];
  }

  // ─── Relationship helpers ───

  can_connect_output_to(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): boolean {
    const fromPort = sourceNode.outputs[fromPortName];
    const toPort = otherNode.inputs[toPortName];

    if (!fromPort)
      throw new Error(
        `Output port '${fromPortName}' not found in node '${this.id}'`,
      );
    if (!toPort)
      throw new Error(
        `Input port '${toPortName}' not found in node '${otherNode.id}'`,
      );
    if (fromPort.node_id === otherNode.id) return false;
    return true;
  }

  isParentOf(sourceNode: Node, otherNode: Node): boolean {
    return sourceNode.id === otherNode.network_id;
  }

  isChildOf(sourceNode: Node, otherNode: Node): boolean {
    return sourceNode.network_id === otherNode.id;
  }

  isSibling(sourceNode: Node, otherNode: Node): boolean {
    return sourceNode.network_id === otherNode.network_id;
  }

  can_connect_input(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): boolean {
    const fromPort = sourceNode.inputs[fromPortName];
    if (!fromPort)
      throw new Error(
        `Input port '${fromPortName}' not found in node '${this.id}'`,
      );
    if (fromPort.node_id === otherNode.id) return false;

    if (this.isSibling(sourceNode, otherNode)) {
      const toPort = otherNode.outputs[toPortName];
      if (!toPort)
        throw new Error(
          `Output port '${toPortName}' not found in node '${otherNode.id}'`,
        );
      return true;
    } else if (this.isParentOf(sourceNode, otherNode)) {
      const toPort = otherNode.inputs[toPortName];
      if (!toPort)
        throw new Error(
          `Output port '${toPortName}' not found in node '${otherNode.id}'`,
        );
      return true;
    } else if (this.isChildOf(sourceNode, otherNode)) {
      const toPort = otherNode.inputs[toPortName];
      if (!toPort)
        throw new Error(
          `Output port '${toPortName}' not found in node '${otherNode.id}'`,
        );
      return true;
    }
    return false;
  }

  connect_input(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): Edge {
    if (!(fromPortName in sourceNode.inputs)) {
      throw new Error(
        `Source node '${sourceNode.id}' does not have input port '${fromPortName}'`,
      );
    }

    let edge: Edge;
    if (this.isSibling(sourceNode, otherNode)) {
      edge = this.graph.add_edge(
        sourceNode.id,
        fromPortName,
        otherNode.id,
        toPortName,
      );
    } else if (this.isParentOf(sourceNode, otherNode)) {
      edge = this.graph.add_edge(
        sourceNode.id,
        fromPortName,
        otherNode.id,
        toPortName,
      );
    } else if (this.isChildOf(sourceNode, otherNode)) {
      edge = this.graph.add_edge(
        otherNode.id,
        toPortName,
        sourceNode.id,
        fromPortName,
      );
    } else {
      throw new Error('Nodes are not siblings or parent/child, cannot connect');
    }
    return edge;
  }

  connect_output(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): Edge {
    return this.connect_input(sourceNode, fromPortName, otherNode, toPortName);
  }

  /** Primary connect method used internally */
  connect_output_to_refactored(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): Edge {
    let fromPort: NodePort | undefined;
    let toPort: NodePort | undefined;

    if (otherNode.network_id === sourceNode.id) {
      // Connection: network input -> child node input (passthrough)
      fromPort = sourceNode.inputs[fromPortName];
      toPort = otherNode.inputs[toPortName];
      console.log(
        `!@!!!!!!!!!CONNECTING TO SUBNET INPUT: ${sourceNode.name} ${fromPortName} -> ${otherNode.name} ${toPortName}`,
      );
    } else if (sourceNode.network_id === otherNode.network_id) {
      // Sibling connection
      fromPort = sourceNode.outputs[fromPortName];
      toPort = otherNode.inputs[toPortName];
    }

    console.log(
      `CONNECTING NODES: ${sourceNode.name} ${fromPortName} -> ${otherNode.name} ${toPortName}`,
    );

    if (!toPort) {
      if (sourceNode.network_id === otherNode.id) {
        toPort = otherNode.outputs[toPortName];
      }
    }

    if (!fromPort) {
      if (sourceNode.id === otherNode.network_id) {
        fromPort = sourceNode.inputs[fromPortName];
      } else {
        throw new Error('FROM PORT STILL NOT FOUND');
      }
    }

    if (!fromPort) {
      throw new Error(
        `Output port '${fromPortName}' not found in node '${this.name}'`,
      );
    }
    if (!toPort) {
      throw new Error(
        `Input port '${toPortName}' not found in node '${otherNode.name}'`,
      );
    }

    if (fromPort.node_id === otherNode.id) {
      throw new Error("Cannot connect a node's output to its own input");
    }

    const existingConnections = this.graph.get_incoming_edges(
      otherNode.id,
      toPortName,
    );
    console.log(
      `  ->Existing Connections on ${otherNode.name} ${toPortName}: ${existingConnections.length}`,
    );

    if (existingConnections.length > 0) {
      if (toPort.isInputOutputPort() || fromPort.isInputOutputPort()) {
        // Allow multiple connections for input/output ports
      } else {
        throw new Error(
          `Error: Input port '${toPortName}' on node '${otherNode.id}' is already connected`,
        );
      }
    }

    return this.graph.add_edge(sourceNode.id, fromPortName, otherNode.id, toPortName);
  }

  connect_node_output_to(
    sourceNode: Node,
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): Edge {
    return this.connect_output_to_refactored(
      sourceNode,
      fromPortName,
      otherNode,
      toPortName,
    );
  }

  connect_to_network_output(
    fromNode: Node,
    fromPortName: string,
    toPortName: string,
  ): void {
    const fromPort = fromNode.outputs[fromPortName];
    const toPort = this.outputs[toPortName];

    if (!fromPort)
      throw new Error(
        `Output port '${fromPortName}' not found in node '${fromNode.id}'`,
      );
    if (!toPort)
      throw new Error(
        `Network Output port '${toPortName}' not found in network '${this.id}'`,
      );

    if (
      fromPort.direction !== PortDirection.OUTPUT &&
      fromPort.direction !== PortDirection.INPUT_OUTPUT
    ) {
      throw new Error('Source port must be an input/output port');
    }
  }

  connect_network_input_to(
    fromPortName: string,
    otherNode: Node,
    toPortName: string,
  ): void {
    const fromPort = this.inputs[fromPortName];
    const toPort = otherNode.inputs[toPortName];

    if (!fromPort)
      throw new Error(
        `Network Input port '${fromPortName}' not found in network '${this.id}'`,
      );
    if (!toPort)
      throw new Error(
        `Input port '${toPortName}' not found in node '${otherNode.id}'`,
      );

    if (fromPort.node_id === otherNode.id) {
      throw new Error("Cannot connect a node's output to its own input");
    }

    if (fromPort.direction !== PortDirection.INPUT_OUTPUT) {
      throw new Error('Source port must be an input/output port');
    }

    this.graph.add_edge(
      this.id,
      fromPort.port_name,
      otherNode.id,
      toPort.port_name,
    );
  }

  compile(builder: any): void {
    // Resolve Data Tunnels
    for (const [portName, port] of Object.entries(this.inputs)) {
      // Placeholder — IR builder not ported
    }
    if ('exec' in this.inputs) {
      const edges = this.graph.get_outgoing_edges(this.id, 'exec');
      for (const edge of edges) {
        const startNode = this.graph.get_node_by_id(edge.to_node_id);
        if (startNode) builder?.compile_chain?.(startNode);
      }
    }
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    if (executionContext) {
      new ExecutionContext(this).from_dict(executionContext);
    }

    if (!this.isNetwork()) {
      throw new Error('compute() called on non-network node');
    }

    const controlOutputs: Record<string, any> = {};
    if ('finished' in this.outputs) {
      controlOutputs['finished'] = true;
    }

    return new ExecutionResult(ExecCommand.CONTINUE, controlOutputs);
  }

  // ─── Factory methods ───

  static createRootNetwork(name: string, type: string): NodeNetwork {
    const graph = new Graph();
    const network = NodeNetwork.create_network(name, type, null, graph);
    console.log('####Created Root Network node with id:', network.id);
    return network;
  }

  createNetwork(name: string, type: string = 'NodeNetworkSystem'): NodeNetwork {
    const networkPath = this.graph.get_path(this.id);
    const nodePath = `${networkPath}/${name}`;

    console.log(
      `Creating sub-network: ${name} in network: ${this.name} of path: ${nodePath}`,
    );

    if (this.graph.get_node_by_path(nodePath)) {
      throw new Error(`Node with id '${name}' already exists in the network`);
    }

    const network = NodeNetwork.create_network(
      name,
      type,
      this.id,
      this.graph,
    );

    console.log(
      `.  ####Added Network node to parent network: ${this.name} with id: ${network.id}`,
    );
    return network;
  }

  createNode(name: string, type: string, ...args: any[]): Node {
    const networkPath = this.graph.get_path(this.id);
    const nodePath = `${networkPath}:${name}`;

    if (this.graph.get_node_by_path(nodePath)) {
      throw new Error(`Node with id '${name}' already exists in the network`);
    }

    console.log(
      `Creating node: ${name} of type: ${type} in network: ${this.name} of path: ${nodePath}`,
    );

    let node: Node;
    try {
      node = Node.create_node(name, type, this.id, ...args);
    } catch (e) {
      throw new Error(`Error creating node '${type}': ${(e as Error).message}`);
    }

    this.graph.add_node(node);
    node.graph = this.graph;
    return node;
  }

  connectNodesByPath(
    fromNodePath: string,
    fromPortName: string,
    toNodePath: string,
    toPortName: string,
  ): Edge {
    const fromNode = this.graph.get_node_by_path(fromNodePath);
    const toNode = this.graph.get_node_by_path(toNodePath);

    if (!fromNode)
      throw new Error(
        `Source node with id '${fromNodePath}' does not exist in the network`,
      );
    if (!toNode)
      throw new Error(
        `Target node with id '${toNodePath}' does not exist in the network '${this.name}'`,
      );

    this.connect_node_output_to(
      fromNode as Node,
      fromPortName,
      toNode as Node,
      toPortName,
    );

    return new Edge(fromNode.id, fromPortName, toNode.id, toPortName);
  }

  connectNodes(
    fromNodeName: string,
    fromPortName: string,
    toNodeName: string,
    toPortName: string,
  ): Edge {
    console.log(
      `Connecting nodes by name: ${fromNodeName} ${fromPortName} ${toNodeName} ${toPortName}`,
    );

    const networkPath = this.graph.get_path(this.id);
    const fromNodePath = `${networkPath}:${fromNodeName}`;
    const toNodePath = `${networkPath}:${toNodeName}`;

    let fromNode = this.graph.get_node_by_path(fromNodePath);
    let toNode = this.graph.get_node_by_path(toNodePath);

    if (fromNodeName === this.name) fromNode = this;
    if (toNodeName === this.name) toNode = this;

    if (!fromNode)
      throw new Error(
        `Source node with id '${fromNodeName}' does not exist in the network`,
      );
    if (!toNode)
      throw new Error(
        `Target node with id '${toNodeName}' does not exist in the network '${this.name}'`,
      );

    this.connect_node_output_to(
      fromNode as Node,
      fromPortName,
      toNode as Node,
      toPortName,
    );

    return new Edge(fromNode.id, fromPortName, toNode.id, toPortName);
  }

  deleteNode(name: string): void {
    console.log(
      ` ---- Deleting node with name: ${name} from network: ${this.name} ${this.id} ${this.isNetwork()}`,
    );

    const networkPath = this.graph.get_path(this.id);
    const nodePath = `${networkPath}:${name}`;

    const node = this.graph.get_node_by_path(nodePath);
    if (!node) {
      throw new Error(`Node with id '${name}' does not exist in the network`);
    }

    this.graph.deleteNode(node.id);
  }

  static deleteAllNodes(): void {
    // No-op: tests should instantiate new graphs
  }

  /** Mirrors Python NodeNetwork.get_input_port_value */
  get_input_port_value(port: NodePort): any {
    if (port._isDirty) {
      if (port.isInputPort() || port.isInputOutputPort()) {
        const upstreamPorts = this.graph.get_upstream_ports(port, true);
        if (upstreamPorts.length > 0) {
          const sourceValuePort = upstreamPorts.pop()! as NodePort;
          const value = sourceValuePort.value;
          for (const upPort of upstreamPorts) {
            (upPort as NodePort)._isDirty = false;
            (upPort as NodePort).value = value;
          }
          port.value = value;
          port._isDirty = false;
        }
      }
    }
    return port.value;
  }
}

// ─────────────────────────────────────────────
// NodeNetworkSystem — mirrors Python NodeNetworkSystem
// ─────────────────────────────────────────────

@NodeNetwork.register('NodeNetworkSystem')
export class NodeNetworkSystem extends NodeNetwork {
  cooking_internally: boolean;

  constructor(
    id: string,
    type: string = 'NodeNetworkSystem',
    networkId: string | null = null,
    graph: Graph | null = null,
    ...kwargs: any[]
  ) {
    super(id, type, networkId, graph);
    this.is_flow_control_node = true;
    this.cooking_internally = false;
    this._isDirty = true;
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    console.log(
      `>>> Computing Root NodeNetworkSystem: ${this.name} with id: ${this.id}`,
    );
    return new ExecutionResult(ExecCommand.CONTINUE);
  }
}

// ─────────────────────────────────────────────
// FlowNodeNetwork — mirrors Python FlowNodeNetwork
// ─────────────────────────────────────────────

@NodeNetwork.register('FlowNodeNetwork')
export class FlowNodeNetwork extends NodeNetwork {
  constructor(
    id: string,
    type: string = 'FlowNodeNetwork',
    networkId: string | null = null,
    graph: Graph | null = null,
    ...kwargs: any[]
  ) {
    super(id, type, networkId, graph);
    this.is_flow_control_node = true;
    this._isDirty = true;
    this.add_control_input('exec');
    this.add_control_output('finished');
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    if (executionContext) {
      new ExecutionContext(this).from_dict(executionContext);
    }

    const controlOutputs: Record<string, any> = {};
    if ('finished' in this.outputs) {
      controlOutputs['finished'] = true;
    }

    const result = new ExecutionResult(ExecCommand.CONTINUE);
    result.control_outputs = controlOutputs;
    return result;
  }
}
