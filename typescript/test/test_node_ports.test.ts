/**
 * Port of python/test/test_node_ports.py
 * Tests NodePort initialization, dirty flag, value setting, and type validation.
 */
import { NodePort, DataPort, ControlPort } from '../src/core/NodePort';
import { ValueType, PortDirection, PortFunction } from '../src/core/Types';
import { Edge } from '../src/core/GraphPrimitives';
import { PORT_TYPE_INPUT } from '../src/core/NodePort';

// ──────────────────────────────────────
// Mock helpers
// ──────────────────────────────────────

interface MockNodeLike {
  id: string;
  inputs: Record<string, NodePort>;
  outputs: Record<string, NodePort>;
}

function makeMockNode(): MockNodeLike {
  return {
    id: Math.random().toString(36).slice(2),
    inputs: {},
    outputs: {},
  };
}

// ──────────────────────────────────────
// TestNodePort
// ──────────────────────────────────────
describe('TestNodePort', () => {
  let mockNode: MockNodeLike;

  beforeEach(() => {
    mockNode = makeMockNode();
  });

  test('test_init_defaults', () => {
    const port = new NodePort(mockNode.id, 'test_port', PORT_TYPE_INPUT); // 1 = INPUT

    expect(port.node_id).toBe(mockNode.id);
    expect(port.port_name).toBe('test_port');
    expect(port.data_type).toBe(ValueType.ANY);
    expect(port.direction).toBe(PortDirection.INPUT);
    expect(port.function).toBe(PortFunction.DATA);
    expect(port.isDirty()).toBe(true);
  });

  test('test_init_control_port', () => {
    const port = new NodePort(mockNode.id, 'exec', 0x81, true); // 0x80 | 1 = Control Input

    expect(port.function).toBe(PortFunction.CONTROL);
    expect(port.isControlPort()).toBe(true);
    expect(port.isDataPort()).toBe(false);
  });

  test('test_dirty_flag', () => {
    const port = new NodePort(mockNode.id, 'dirty_port', PORT_TYPE_INPUT);

    port.markClean();
    expect(port.isDirty()).toBe(false);

    port.markDirty();
    expect(port.isDirty()).toBe(true);
  });

  test('test_set_value_updates_dirty_flag', () => {
    const port = new NodePort(mockNode.id, 'val_port', PORT_TYPE_INPUT);
    port.setValue(100);

    expect(port.getValue()).toBe(100);
    expect(port.isDirty()).toBe(false);
  });

  test('test_value_type_validation_warning', () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    const port = new NodePort(mockNode.id, 'int_port', PORT_TYPE_INPUT, false, ValueType.INT);
    port.setValue('not an int');

    expect(warnSpy).toHaveBeenCalled();
    const warnMsg = warnSpy.mock.calls[0][0] as string;
    expect(warnMsg).toMatch(/expected.*int/i);

    warnSpy.mockRestore();
  });
});

// ──────────────────────────────────────
// TestValueTypeable
// ──────────────────────────────────────
describe('TestValueTypeable', () => {
  test('test_int_validation', () => {
    expect(ValueType.validate(10, ValueType.INT)).toBe(true);
    expect(ValueType.validate('10', ValueType.INT)).toBe(false);
  });

  test('test_any_validation', () => {
    expect(ValueType.validate('foo', ValueType.ANY)).toBe(true);
    expect(ValueType.validate(123, ValueType.ANY)).toBe(true);
  });
});
