import { ValueType, PortFunction, PortDirection } from './Types';

// ─────────────────────────────────────────────
// Port Interfaces
// ─────────────────────────────────────────────

export abstract class INodePort {
  abstract markDirty(): void;
  abstract markClean(): void;
  abstract isDirty(): boolean;
  abstract isDataPort(): boolean;
  abstract isControlPort(): boolean;
  abstract isInputPort(): boolean;
  abstract isOutputPort(): boolean;
  abstract isInputOutputPort(): boolean;
  abstract setValue(value: any): void;
  abstract getValue(): any;
}

export abstract class IInputControlPort extends INodePort {}
export abstract class IOutputControlPort extends INodePort {}
export abstract class IInputDataPort extends INodePort {}
export abstract class IOutputDataPort extends INodePort {}

// ─────────────────────────────────────────────
// Graph Node Interface
// ─────────────────────────────────────────────

export abstract class IGraphNode {
  name!: string;
  id!: string;
  uuid!: string;
  network_id!: string | null;

  abstract isNetwork(): boolean;
}

// ─────────────────────────────────────────────
// Node Interface
// ─────────────────────────────────────────────

export abstract class INode extends IGraphNode {
  abstract isDataNode(): boolean;
  abstract isFlowControlNode(): boolean;
  abstract isDirty(): boolean;
  abstract markDirty(): void;
  abstract markClean(): void;

  abstract delete_input(portName: string): void;
  abstract delete_output(portName: string): void;

  abstract add_control_input(portName: string): IInputControlPort;
  abstract add_control_output(portName: string): IOutputControlPort;
  abstract add_data_input(portName: string, dataType?: ValueType): IInputDataPort;
  abstract add_data_output(portName: string, dataType?: ValueType): IOutputDataPort;

  abstract get_input_ports(restrictTo?: PortFunction | null): INodePort[];
  abstract get_output_ports(restrictTo?: PortFunction | null): INodePort[];
  abstract get_output_data_ports(): INodePort[];
  abstract get_output_control_ports(): INodePort[];
  abstract get_input_data_ports(): INodePort[];
  abstract get_input_control_ports(): INodePort[];

  abstract get_input_data_port(portName: string): INodePort;
  abstract get_output_data_port(portName: string): INodePort;
  abstract get_input_control_port(portName: string): INodePort;
  abstract get_output_control_port(portName: string): INodePort;

  abstract precompute(): void;
  abstract postcompute(): void;
  abstract all_data_inputs_clean(): boolean;
  abstract all_data_outputs_clean(): boolean;

  abstract compute(executionContext?: any): Promise<IExecutionResult>;
  abstract compile(builder: any): void;
  abstract generate_IRC(): void;
}

export abstract class INodeNetwork extends INode {}

// ─────────────────────────────────────────────
// Execution Interfaces
// ─────────────────────────────────────────────

export abstract class IExecutionContext {
  abstract get_port_value(port: INodePort): any;
  abstract to_dict(): Record<string, any>;
  abstract from_dict(contextDict: Record<string, any>): void;
}

export abstract class IExecutionResult {
  abstract deserialize_result(node: INode): void;
}
