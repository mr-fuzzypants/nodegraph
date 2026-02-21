/**
 * Port direction enum — mirrors Python PortDirection.
 */
export enum PortDirection {
  INPUT = 'INPUT',
  OUTPUT = 'OUTPUT',
  INPUT_OUTPUT = 'INPUT_OUTPUT',
}

/**
 * Port function enum — mirrors Python PortFunction.
 */
export enum PortFunction {
  DATA = 'DATA',
  CONTROL = 'CONTROL',
}

/**
 * Supported value types for data ports.
 */
export enum ValueType {
  ANY = 'any',
  INT = 'int',
  FLOAT = 'float',
  STRING = 'string',
  BOOL = 'bool',
  DICT = 'dict',
  ARRAY = 'array',
  OBJECT = 'object',
  VECTOR = 'vector',
  MATRIX = 'matrix',
  COLOR = 'color',
  BINARY = 'binary',
}

// Augment the ValueType namespace with a static `validate` function
// (mirrors Python's ValueType.validate static method)
export namespace ValueType {
  export function validate(value: any, dataType: ValueType): boolean {
    if (dataType === ValueType.ANY) return true;
    if (value === null || value === undefined) return true; // Allow None equivalent

    switch (dataType) {
      case ValueType.INT:
        return Number.isInteger(value);
      case ValueType.FLOAT:
        // Allow ints to pass as floats (mirrors Python behaviour)
        return typeof value === 'number';
      case ValueType.STRING:
        return typeof value === 'string';
      case ValueType.BOOL:
        return typeof value === 'boolean';
      case ValueType.DICT:
        return (
          typeof value === 'object' &&
          !Array.isArray(value) &&
          value !== null
        );
      case ValueType.ARRAY:
        return Array.isArray(value);
      case ValueType.OBJECT:
        return true;
      case ValueType.VECTOR:
        return Array.isArray(value);
      case ValueType.MATRIX:
        return Array.isArray(value);
      case ValueType.COLOR:
        return typeof value === 'string' || Array.isArray(value);
      case ValueType.BINARY:
        return value instanceof Uint8Array || value instanceof ArrayBuffer;
      default:
        return false;
    }
  }
}

/**
 * Kind discriminator for node types.
 */
export enum NodeKind {
  FUNCTION = 'FUNCTION',
  NETWORK = 'NETWORK',
}

// Legacy DataType alias — matches Python's DataType = ValueType
export const DataType = ValueType;
