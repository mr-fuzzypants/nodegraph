import { v4 as uuidv4 } from 'uuid';
import {
  IExecutionContext,
  IExecutionResult,
  INode,
  INodePort,
  IInputControlPort,
  IOutputControlPort,
  IInputDataPort,
  IOutputDataPort,
} from './Interface';
import { ValueType, PortFunction, NodeKind } from './Types';
import {
  NodePort,
  InputDataPort,
  OutputDataPort,
  InputControlPort,
  OutputControlPort,
} from './NodePort';
import { GraphNode } from './GraphPrimitives';

// ─────────────────────────────────────────────
// PluginRegistry — mirrors Python PluginRegistry
// ─────────────────────────────────────────────

export class PluginRegistry {
  private static _registry: Map<string, typeof Node> = new Map();

  /** Decorator factory to register a node class with a specific type name. */
  static register(typeName: string) {
    return function <T extends typeof Node>(subclass: T): T {
      if (PluginRegistry._registry.has(typeName)) {
        throw new Error(`Node type '${typeName}' is already registered.`);
      }
      PluginRegistry._registry.set(typeName, subclass as unknown as typeof Node);
      return subclass;
    };
  }

  static get_node_class(typeName: string): typeof Node | undefined {
    return PluginRegistry._registry.get(typeName);
  }

  static create_node(nodeId: string, typeName: string, ...args: any[]): Node {
    const NodeClass = PluginRegistry.get_node_class(typeName);
    if (!NodeClass) throw new Error(`Unknown node type '${typeName}'`);
    return new (NodeClass as any)(nodeId, typeName, ...args);
  }

  static get_registered_types(): string[] {
    return Array.from(PluginRegistry._registry.keys());
  }
}

// ─────────────────────────────────────────────
// Node — base class for all computation nodes
// ─────────────────────────────────────────────

export abstract class Node extends INode {
  // Separate registry from PluginRegistry (mirrors Python Node._node_registry)
  static _node_registry: Map<string, typeof Node> = new Map();

  /** Decorator factory to register a node class with a specific type name. */
  static register(typeName: string) {
    return function <T extends typeof Node>(subclass: T): T {
      if (Node._node_registry.has(typeName)) {
        throw new Error(`Node type '${typeName}' is already registered.`);
      }
      Node._node_registry.set(typeName, subclass as unknown as typeof Node);
      return subclass;
    };
  }

  static create_node(nodeId: string, typeName: string, ...args: any[]): Node {
    if (!Node._node_registry.has(typeName)) {
      throw new Error(`Unknown node type '${typeName}'`);
    }
    const NodeClass = Node._node_registry.get(typeName)!;
    return new (NodeClass as any)(nodeId, typeName, ...args);
  }

  // ─── Instance state ───
  name: string;
  id: string;
  uuid: string;
  type: string;
  network_id: string | null;
  inputs: Record<string, NodePort>;
  outputs: Record<string, NodePort>;
  is_flow_control_node: boolean;
  is_loop_node: boolean;
  _isDirty: boolean;
  graph: any; // set by NodeNetwork when added
  path: string;
  kind: NodeKind;

  constructor(
    name: string,
    type: string,
    networkId: string | null = null,
    inputs?: Record<string, NodePort>,
    outputs?: Record<string, NodePort>,
    /** absorb extra kwargs forwarded from subclasses */
    ...rest: any[]
  ) {
    super();
    this.name = name;
    this.id = uuidv4().replace(/-/g, '');
    this.uuid = uuidv4().replace(/-/g, '');
    this.type = type;
    this.network_id = networkId;
    this.inputs = inputs ?? {};
    this.outputs = outputs ?? {};
    this.is_flow_control_node = false;
    this.is_loop_node = false;
    this._isDirty = true;
    this.graph = null;
    this.path = ' path node computed at runtime ';
    this.kind = NodeKind.FUNCTION;
  }

  isNetwork(): boolean {
    return this.kind === NodeKind.NETWORK;
  }

  isDataNode(): boolean {
    return !this.is_flow_control_node;
  }

  isFlowControlNode(): boolean {
    return this.is_flow_control_node;
  }

  markDirty(): void {
    this._isDirty = true;
  }

  markClean(): void {
    this._isDirty = false;
  }

  isDirty(): boolean {
    return this._isDirty;
  }

  /**
   * Snapshot this node's internal execution state for checkpoint/resume.
   *
   * The base implementation captures every output port value. Subclasses that
   * hold private loop counters or other transient state (e.g. ForLoopNode's
   * _loopIndex / _loopActive) should override this and spread super's result:
   *
   *   serializeState() {
   *     return { ...super.serializeState(), _loopIndex: this._loopIndex, _loopActive: this._loopActive };
   *   }
   */
  serializeState(): Record<string, unknown> {
    const portValues: Record<string, unknown> = {};
    for (const [k, p] of Object.entries(this.outputs)) {
      portValues[`out:${k}`] = (p as any).value;
    }
    for (const [k, p] of Object.entries(this.inputs)) {
      portValues[`in:${k}`] = (p as any).value;
    }
    return portValues;
  }

  /**
   * Restore internal execution state from a previously captured snapshot.
   * The base implementation restores port values. Subclasses should override
   * to restore their own private fields as well.
   */
  deserializeState(state: Record<string, unknown>): void {
    for (const [key, value] of Object.entries(state)) {
      if (key.startsWith('out:')) {
        const portName = key.slice(4);
        if (this.outputs[portName]) (this.outputs[portName] as any).setValue(value);
      } else if (key.startsWith('in:')) {
        const portName = key.slice(3);
        if (this.inputs[portName]) (this.inputs[portName] as any).setValue(value);
      }
    }
  }

  delete_input(portName: string): void {
    if (portName in this.inputs) {
      delete this.inputs[portName];
    }
  }

  delete_output(portName: string): void {
    if (portName in this.outputs) {
      delete this.outputs[portName];
    }
  }

  add_control_input(portName: string): InputControlPort {
    const port = new InputControlPort(this.id, portName);
    this.inputs[portName] = port;
    return port;
  }

  add_control_output(portName: string): OutputControlPort {
    const port = new OutputControlPort(this.id, portName);
    this.outputs[portName] = port;
    return port;
  }

  add_data_input(portName: string, dataType: ValueType = ValueType.ANY): InputDataPort {
    if (portName in this.inputs) {
      throw new Error(
        `Data input port '${portName}' already exists in node '${this.id}'`,
      );
    }
    const port = new InputDataPort(this.id, portName, dataType);
    this.inputs[portName] = port;
    return port;
  }

  add_data_output(portName: string, dataType: ValueType = ValueType.ANY): OutputDataPort {
    if (portName in this.outputs) {
      throw new Error(
        `Data output port '${portName}' already exists in node '${this.id}'`,
      );
    }
    const port = new OutputDataPort(this.id, portName, dataType);
    this.outputs[portName] = port;
    return port;
  }

  get_input_ports(restrictTo: PortFunction | null = null): NodePort[] {
    const all = Object.values(this.inputs);
    if (restrictTo === null) return all;
    return all.filter((p) => p.function === restrictTo);
  }

  get_output_ports(restrictTo: PortFunction | null = null): NodePort[] {
    const all = Object.values(this.outputs);
    if (restrictTo === null) return all;
    return all.filter((p) => p.function === restrictTo);
  }

  get_output_data_ports(): NodePort[] {
    return this.get_output_ports(PortFunction.DATA);
  }

  get_output_control_ports(): NodePort[] {
    return this.get_output_ports(PortFunction.CONTROL);
  }

  get_input_data_ports(): NodePort[] {
    return this.get_input_ports(PortFunction.DATA);
  }

  get_input_control_ports(): NodePort[] {
    return this.get_input_ports(PortFunction.CONTROL);
  }

  get_input_data_port(portName: string): NodePort {
    const port = this.inputs[portName];
    if (!port) throw new Error(`Input port '${portName}' not found in node '${this.id}'`);
    if (!port.isDataPort())
      throw new Error(
        `Input port '${portName}' in node '${this.id}' is not a data port`,
      );
    return port;
  }

  get_output_data_port(portName: string): NodePort {
    const port = this.outputs[portName];
    if (!port)
      throw new Error(`Output port '${portName}' not found in node '${this.id}'`);
    if (!port.isDataPort())
      throw new Error(
        `Output port '${portName}' in node '${this.id}' is not a data port`,
      );
    return port;
  }

  get_input_control_port(portName: string): NodePort {
    const port = this.inputs[portName];
    if (!port)
      throw new Error(`Input port '${portName}' not found in node '${this.id}'`);
    if (!port.isControlPort())
      throw new Error(
        `Input port '${portName}' in node '${this.id}' is not a control port`,
      );
    return port;
  }

  get_output_control_port(portName: string): NodePort {
    const port = this.outputs[portName];
    if (!port)
      throw new Error(`Output port '${portName}' not found in node '${this.id}'`);
    if (!port.isControlPort())
      throw new Error(
        `Output port '${portName}' in node '${this.id}' is not a control port`,
      );
    return port;
  }

  precompute(): void {
    console.log(`PRECOMPUTE: node '${this.id}'`);
  }

  postcompute(): void {
    this.dump_dirty_states();
    if (!this.all_data_inputs_clean()) {
      throw new Error(`postcompute: not all data inputs are clean on node '${this.id}'`);
    }
    if (!this.all_data_outputs_clean()) {
      throw new Error(`postcompute: not all data outputs are clean on node '${this.id}'`);
    }
    this._isDirty = false;
  }

  all_data_inputs_clean(): boolean {
    for (const port of this.get_input_data_ports()) {
      if (port._isDirty) return false;
    }
    return true;
  }

  all_data_outputs_clean(): boolean {
    for (const port of this.get_output_data_ports()) {
      if (port._isDirty) return false;
    }
    return true;
  }

  dump_dirty_states(): void {
    console.log(`  Node '${this.id}' port dirty states:`);
    const ctrlIns = this.get_input_control_ports();
    console.log(`.    Control Inputs: (${ctrlIns.length})`);
    for (const p of ctrlIns) {
      console.log(
        `.       Input Port [${(p as any).port_name}] dirty: ${p.isDirty()}; active: ${(p as any).isActive?.() ?? 'N/A'}`,
      );
    }
    const ctrlOuts = this.get_output_control_ports();
    console.log(`.    Control Outputs: (${ctrlOuts.length})`);
    for (const p of ctrlOuts) {
      console.log(
        `.       Output Port [${(p as any).port_name}] dirty: ${p.isDirty()}; active: ${(p as any).isActive?.() ?? 'N/A'}`,
      );
    }
    const dataIns = this.get_input_data_ports();
    console.log(`.    Data Inputs: (${dataIns.length})`);
    for (const p of dataIns) {
      console.log(`.       Input Port [${(p as any).port_name}] dirty: ${p.isDirty()}; value: ${(p as any).value}`);
    }
    const dataOuts = this.get_output_data_ports();
    console.log(`.    Data Outputs: (${dataOuts.length})`);
    for (const p of dataOuts) {
      console.log(`.       Output Port [${(p as any).port_name}] dirty: ${p.isDirty()}; value: ${(p as any).value}`);
    }
  }

  abstract compute(executionContext?: any): Promise<IExecutionResult>;

  compile(builder: any): void {
    // Placeholder
  }

  generate_IRC(): void {
    // Placeholder
  }
}
