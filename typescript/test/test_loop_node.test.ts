/**
 * Port of python/test/test_loop_node.py
 * Tests loop execution: basic, parallel-branch, and nested loops.
 */
import { Node } from '../src/core/Node';
import { NodeNetwork } from '../src/core/NodeNetwork';
import {
  ExecCommand,
  ExecutionResult,
  Executor,
} from '../src/core/Executor';
import {
  InputControlPort,
  OutputControlPort,
  InputDataPort,
  OutputDataPort,
} from '../src/core/NodePort';
import { ValueType } from '../src/core/Types';

// ──────────────────────────────────────
// ForLoopNode
// ──────────────────────────────────────

@Node.register('ForLoopNode')
class ForLoopNode extends Node {
  private _current_index: number | null = null;

  constructor(id: string, type: string = 'ForLoopNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.is_flow_control_node = true;

    this.inputs['exec'] = new InputControlPort(this.id, 'exec');
    this.inputs['start'] = new InputDataPort(this.id, 'start', ValueType.INT);
    this.inputs['end'] = new InputDataPort(this.id, 'end', ValueType.INT);

    this.outputs['loop_body'] = new OutputControlPort(this.id, 'loop_body');
    this.outputs['completed'] = new OutputControlPort(this.id, 'completed');
    this.outputs['index'] = new OutputDataPort(this.id, 'index', ValueType.INT);
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    const dataInputs = executionContext?.['data_inputs'] ?? {};
    let startVal: number = dataInputs['start'] ?? this.inputs['start'].value ?? 0;
    let endVal: number = dataInputs['end'] ?? this.inputs['end'].value ?? 0;

    if (this._current_index === null) {
      this._current_index = startVal;
    }

    if (this._current_index < endVal) {
      const iterVal = this._current_index;
      (this.outputs['index'] as OutputDataPort).setValue(iterVal);
      this._current_index += 1;

      const result = new ExecutionResult(ExecCommand.LOOP_AGAIN);
      result.control_outputs['loop_body'] = true;
      return result;
    } else {
      this._current_index = null;
      const result = new ExecutionResult(ExecCommand.COMPLETED);
      result.control_outputs['completed'] = true;
      return result;
    }
  }
}

// ──────────────────────────────────────
// CounterNode
// ──────────────────────────────────────

@Node.register('CounterNode')
class CounterNode extends Node {
  public count: number = 0;
  public last_val: number = -1;

  constructor(id: string, type: string = 'CounterNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.is_flow_control_node = true;
    this.inputs['exec'] = new InputControlPort(this.id, 'exec');
    this.inputs['val'] = new InputDataPort(this.id, 'val', ValueType.INT);
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    this.count += 1;
    const val = await this.inputs['val'].getValue();
    if (val !== null && val !== undefined) {
      this.last_val = val as number;
    }
    return new ExecutionResult(ExecCommand.CONTINUE);
  }
}

// ──────────────────────────────────────
// Tests
// ──────────────────────────────────────

describe('TestLoopNode', () => {
  test('test_loop_execution', async () => {
    const net = NodeNetwork.createRootNetwork('LoopNet', 'NodeNetworkSystem');
    const loopNode = net.createNode('loop_1', 'ForLoopNode') as ForLoopNode;
    const counter = net.createNode('counter_1', 'CounterNode') as CounterNode;

    loopNode.inputs['start'].setValue(0);
    loopNode.inputs['end'].setValue(5);

    net.graph.add_edge(loopNode.id, 'loop_body', counter.id, 'exec');
    net.graph.add_edge(loopNode.id, 'index', counter.id, 'val');

    await new Executor(net.graph).cook_flow_control_nodes(loopNode);

    expect(counter.count).toBe(5);
    expect(counter.last_val).toBe(4);
  });

  test('test_parallel_loop_branches', async () => {
    const net = NodeNetwork.createRootNetwork('ParallelLoopNet', 'NodeNetworkSystem');
    const loopNode = net.createNode('loop_p', 'ForLoopNode') as ForLoopNode;
    const counterA = net.createNode('counter_a', 'CounterNode') as CounterNode;
    const counterB = net.createNode('counter_b', 'CounterNode') as CounterNode;

    loopNode.inputs['start'].setValue(0);
    loopNode.inputs['end'].setValue(3);

    net.graph.add_edge(loopNode.id, 'loop_body', counterA.id, 'exec');
    net.graph.add_edge(loopNode.id, 'loop_body', counterB.id, 'exec');
    net.graph.add_edge(loopNode.id, 'index', counterA.id, 'val');
    net.graph.add_edge(loopNode.id, 'index', counterB.id, 'val');

    await new Executor(net.graph).cook_flow_control_nodes(loopNode);

    expect(counterA.count).toBe(3);
    expect(counterB.count).toBe(3);
    expect(counterA.last_val).toBe(2);
    expect(counterB.last_val).toBe(2);
  });

  test('test_nested_loops', async () => {
    const net = NodeNetwork.createRootNetwork('NestedLoopNet', 'NodeNetworkSystem');
    const outerLoop = net.createNode('OuterLoop', 'ForLoopNode') as ForLoopNode;
    const innerLoop = net.createNode('InnerLoop', 'ForLoopNode') as ForLoopNode;
    const counter = net.createNode('Counter', 'CounterNode') as CounterNode;

    outerLoop.inputs['start'].setValue(0);
    outerLoop.inputs['end'].setValue(3); // 0, 1, 2

    innerLoop.inputs['start'].setValue(0);
    innerLoop.inputs['end'].setValue(2); // 0, 1

    net.graph.add_edge(outerLoop.id, 'loop_body', innerLoop.id, 'exec');
    net.graph.add_edge(innerLoop.id, 'loop_body', counter.id, 'exec');
    net.graph.add_edge(innerLoop.id, 'index', counter.id, 'val');

    await new Executor(net.graph).cook_flow_control_nodes(outerLoop);

    // Outer runs 3 times, each fires inner 2 times → 6 total counter hits
    expect(counter.count).toBe(6);
    expect(counter.last_val).toBe(1);
  });
});
