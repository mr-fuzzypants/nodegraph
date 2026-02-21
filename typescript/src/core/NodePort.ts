import { PortDirection, PortFunction, ValueType } from './Types';
import { INodePort } from './Interface';

// ─────────────────────────────────────────────
// Legacy integer bit-flag constants (mirrors Python NodePort.py)
// ─────────────────────────────────────────────
export const PORT_TYPE_INPUT = 1;
export const PORT_TYPE_OUTPUT = 2;
export const PORT_TYPE_INPUTOUTPUT = 4;
export const PORT_TYPE_OUTPUTINPUT = 8;
export const PORT_TYPE_CONTROL = 0x80;

export const CONTROL_PORT = 0;
export const DATA_PORT = 1;
export const ANY_PORT = 2;

// Legacy alias (mirrors Python's DataType = ValueType)
export { ValueType as DataType };
// Re-export enums for backwards compat
export { PortDirection, PortFunction };

// ─────────────────────────────────────────────
// NodePort — base port class
// ─────────────────────────────────────────────

export class NodePort extends INodePort {
  node_id: string;
  port_name: string;
  port_type: number;
  data_type: ValueType;
  _isDirty: boolean;
  value: any;
  direction: PortDirection;
  function: PortFunction;

  constructor(
    nodeId: string,
    portName: string,
    portType: number,
    isControl: boolean = false,
    dataType: ValueType = ValueType.ANY,
  ) {
    super();
    this.node_id = nodeId;
    this.port_name = portName;
    this.port_type = portType;
    this.data_type = dataType;
    this._isDirty = true;
    this.value = this._get_default_for_type(dataType);

    // Infer direction from legacy flags
    this.direction = PortDirection.INPUT;
    if (this.port_type & PORT_TYPE_OUTPUT) {
      this.direction = PortDirection.OUTPUT;
    } else if (this.port_type & PORT_TYPE_INPUTOUTPUT) {
      this.direction = PortDirection.INPUT_OUTPUT;
    }

    this.function =
      isControl || (this.port_type & PORT_TYPE_CONTROL) !== 0
        ? PortFunction.CONTROL
        : PortFunction.DATA;

    if (isControl) {
      this.port_type |= PORT_TYPE_CONTROL;
    }
  }

  _get_default_for_type(dtype: ValueType): any {
    if (dtype === ValueType.INT) return 0;
    if (dtype === ValueType.FLOAT) return 0.0;
    if (dtype === ValueType.STRING) return '';
    if (dtype === ValueType.BOOL) return false;
    if (dtype === ValueType.ARRAY) return [];
    if (dtype === ValueType.DICT) return {};
    return null;
  }

  markDirty(): void {
    if (this._isDirty) return; // Prevent infinite recursion
    this._isDirty = true;
  }

  markClean(): void {
    this._isDirty = false;
  }

  isDirty(): boolean {
    return this._isDirty;
  }

  isDataPort(): boolean {
    return this.function === PortFunction.DATA;
  }

  isControlPort(): boolean {
    return this.function === PortFunction.CONTROL;
  }

  isInputPort(): boolean {
    return this.direction === PortDirection.INPUT;
  }

  isOutputPort(): boolean {
    return this.direction === PortDirection.OUTPUT;
  }

  isInputOutputPort(): boolean {
    return this.direction === PortDirection.INPUT_OUTPUT;
  }

  setValue(value: any): void {
    if (!ValueType.validate(value, this.data_type)) {
      // Log warning (mirrors Python logger.warning behaviour)
      console.warn(
        `Port '${this.port_name}' expected ${this.data_type}, got ${typeof value}. Value=${value}`,
      );
    }
    this.value = value;
    this._isDirty = false;
  }

  getValue(): any {
    return this.value;
  }
}

// ─────────────────────────────────────────────
// DataPort / ControlPort subclasses
// ─────────────────────────────────────────────

export class DataPort extends NodePort {
  incoming_connections: any[] = [];
  outgoing_connections: any[] = [];

  constructor(
    nodeId: string,
    portName: string,
    portType: number,
    dataType: ValueType = ValueType.ANY,
  ) {
    super(nodeId, portName, portType, false, dataType);
  }

  async getValue(currentPort?: any): Promise<any> {
    return this.value;
  }
}

export class ControlPort extends NodePort {
  incoming_connections: any[] = [];
  outgoing_connections: any[] = [];

  constructor(nodeId: string, portName: string, portType: number) {
    super(nodeId, portName, portType | PORT_TYPE_CONTROL, true);
  }

  activate(currentPort?: any): void {
    this.setValue(true);
  }

  deactivate(): void {
    this.setValue(false);
  }

  isActive(): boolean {
    return this.getValue() === true;
  }
}

// ─────────────────────────────────────────────
// Concrete typed port classes
// ─────────────────────────────────────────────

export class InputDataPort extends DataPort {
  incoming_connections: any[];

  constructor(nodeId: string, portName: string, dataType: ValueType = ValueType.ANY) {
    super(nodeId, portName, PORT_TYPE_INPUT, dataType);
    this.incoming_connections = [];
  }
}

export class InputControlPort extends ControlPort {
  incoming_connections: any[];

  constructor(nodeId: string, portName: string) {
    super(nodeId, portName, PORT_TYPE_INPUT | PORT_TYPE_CONTROL);
    this.incoming_connections = [];
  }
}

export class InputOutputDataPort extends DataPort {
  incoming_connections: any[];
  outgoing_connections: any[];

  constructor(nodeId: string, portName: string, dataType: ValueType = ValueType.ANY) {
    super(nodeId, portName, PORT_TYPE_INPUTOUTPUT, dataType);
    this.incoming_connections = [];
    this.outgoing_connections = [];
  }
}

export class InputOutputControlPort extends ControlPort {
  incoming_connections: any[];
  outgoing_connections: any[];

  constructor(nodeId: string, portName: string) {
    super(nodeId, portName, PORT_TYPE_INPUTOUTPUT | PORT_TYPE_CONTROL);
    this.incoming_connections = [];
    this.outgoing_connections = [];
  }
}

export class OutputDataPort extends DataPort {
  outgoing_connections: any[];

  constructor(nodeId: string, portName: string, dataType: ValueType = ValueType.ANY) {
    super(nodeId, portName, PORT_TYPE_OUTPUT, dataType);
    this.outgoing_connections = [];
  }
}

export class OutputControlPort extends ControlPort {
  outgoing_connections: any[];

  constructor(nodeId: string, portName: string) {
    super(nodeId, portName, PORT_TYPE_OUTPUT | PORT_TYPE_CONTROL);
    this.outgoing_connections = [];
  }
}
