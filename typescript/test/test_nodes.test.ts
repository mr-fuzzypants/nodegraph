/**
 * Port of python/test/test_nodes.py
 * Tests basic Node creation, port management, dirty flags, and validation.
 */
import { Node } from '../src/core/Node';
import { NodeNetwork } from '../src/core/NodeNetwork';
import { DataPort, ControlPort } from '../src/core/NodePort';
import { ValueType } from '../src/core/Types';
import { ExecCommand, ExecutionResult } from '../src/core/Executor';

// ──────────────────────────────────────
// Mock node registered for tests
// ──────────────────────────────────────
@Node.register('MockNodeOne')
class MockNodeOne extends Node {
  constructor(name: string, type: string = 'MockNodeOne', networkId: string | null = null) {
    super(name, type, networkId);
  }

  async compute(): Promise<ExecutionResult> {
    return new ExecutionResult(ExecCommand.CONTINUE);
  }
}

// ──────────────────────────────────────
// TestNode
// ──────────────────────────────────────
describe('TestNode', () => {
  let node: MockNodeOne;

  beforeEach(() => {
    node = new MockNodeOne('test_node_1', 'TestType');
  });

  test('test_node_initialization', () => {
    expect(node.name).toBe('test_node_1');
    expect(node.type).toBe('TestType');
    expect(node.isDirty()).toBe(true);
    expect(Object.keys(node.inputs).length).toBe(0);
    expect(Object.keys(node.outputs).length).toBe(0);
    expect(node.isFlowControlNode()).toBe(false);
    expect(node.isDataNode()).toBe(true);
  });

  test('test_dirty_flag_management', () => {
    node.markClean();
    expect(node.isDirty()).toBe(false);

    node.markDirty();
    expect(node.isDirty()).toBe(true);
  });

  test('test_add_data_input', () => {
    const port = node.add_data_input('in_a');

    expect('in_a' in node.inputs).toBe(true);
    expect(node.inputs['in_a']).toBe(port);
    expect(port).toBeInstanceOf(DataPort);
    expect(port.port_name).toBe('in_a');
    expect(port.data_type).toBe(ValueType.ANY);
  });

  test('test_add_data_output', () => {
    const port = node.add_data_output('out_result');

    expect('out_result' in node.outputs).toBe(true);
    expect(node.outputs['out_result']).toBe(port);
    expect(port).toBeInstanceOf(DataPort);
    expect(port.port_name).toBe('out_result');
  });

  test('test_add_control_input', () => {
    const port = node.add_control_input('exec');

    expect('exec' in node.inputs).toBe(true);
    expect(node.inputs['exec']).toBe(port);
    expect(port).toBeInstanceOf(ControlPort);
    expect(port.isControlPort()).toBe(true);
  });

  test('test_add_control_output', () => {
    const port = node.add_control_output('then');

    expect('then' in node.outputs).toBe(true);
    expect(node.outputs['then']).toBe(port);
    expect(port).toBeInstanceOf(ControlPort);
    expect(port.isControlPort()).toBe(true);
  });

  test('test_duplicate_port_name_error', () => {
    node.add_data_input('dup_port');
    expect(() => node.add_data_input('dup_port')).toThrow(/already exists/);

    node.add_data_output('dup_port_out');
    expect(() => node.add_data_output('dup_port_out')).toThrow(/already exists/);
  });

  test('test_typed_ports', async () => {
    const intPort = node.add_data_input('int_input_t', ValueType.INT);
    const floatPort = node.add_data_output('float_output_t', ValueType.FLOAT);

    expect(intPort.data_type).toBe(ValueType.INT);
    expect(floatPort.data_type).toBe(ValueType.FLOAT);

    // Valid assignment
    intPort.setValue(42);
    const val = await intPort.getValue();
    expect(val).toBe(42);

    // Invalid assignment — current impl logs warning, does not throw
    intPort.setValue('not an int');
    const val2 = await intPort.getValue();
    expect(val2).toBe('not an int');
  });

  test('test_helper_get_ports', () => {
    node.add_data_input('d_in', ValueType.INT);
    node.add_control_input('c_in');
    node.add_data_output('d_out', ValueType.FLOAT);
    node.add_control_output('c_out');

    const dIn = node.get_input_data_port('d_in');
    expect(dIn).not.toBeNull();
    expect(dIn.port_name).toBe('d_in');
    expect((dIn as any).data_type).toBe(ValueType.INT);

    const cIn = node.get_input_control_port('c_in');
    expect(cIn).not.toBeNull();
    expect(cIn.port_name).toBe('c_in');

    expect(() => node.get_input_data_port('non_existent')).toThrow();
  });

  test('test_delete_input_port', () => {
    node.add_data_input('to_delete');
    expect('to_delete' in node.inputs).toBe(true);

    node.delete_input('to_delete');
    expect('to_delete' in node.inputs).toBe(false);
  });

  test('test_delete_output_port', () => {
    node.add_data_output('to_delete');
    expect('to_delete' in node.outputs).toBe(true);

    node.delete_output('to_delete');
    expect('to_delete' in node.outputs).toBe(false);
  });
});

// ──────────────────────────────────────
// TestDataTypeValidation
// ──────────────────────────────────────
describe('TestDataTypeValidation', () => {
  test('test_validate_methods', () => {
    expect(ValueType.validate(10, ValueType.INT)).toBe(true);
    expect(ValueType.validate(10.5, ValueType.INT)).toBe(false);

    expect(ValueType.validate(10.5, ValueType.FLOAT)).toBe(true);
    expect(ValueType.validate(10, ValueType.FLOAT)).toBe(true); // int allowed as float

    expect(ValueType.validate('hello', ValueType.STRING)).toBe(true);
    expect(ValueType.validate(123, ValueType.STRING)).toBe(false);

    expect(ValueType.validate([1, 2], ValueType.ARRAY)).toBe(true);
    expect(ValueType.validate({ a: 1 }, ValueType.DICT)).toBe(true);
  });
});
