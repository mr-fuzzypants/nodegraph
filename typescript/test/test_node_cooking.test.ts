/**
 * Port of python/test/test_node_cooking.py
 * Tests data-node dependency resolution and cooking order.
 */
import { Node } from '../src/core/Node';
import { NodeNetwork } from '../src/core/NodeNetwork';
import { ExecCommand, ExecutionResult, Executor } from '../src/core/Executor';
import { InputDataPort, OutputDataPort } from '../src/core/NodePort';
import { ValueType } from '../src/core/Types';

// Global execution log
let EXECUTION_LOG: string[] = [];

@Node.register('CookingTestNode')
class CookingTestNode extends Node {
  compute_count: number;

  constructor(id: string, type: string = 'CookingTestNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.compute_count = 0;
    this.inputs['in'] = new InputDataPort(this.id, 'in', ValueType.INT);
    this.outputs['out'] = new OutputDataPort(this.id, 'out', ValueType.INT);
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    expect(executionContext).not.toBeNull();

    const node = this.graph.find_node_by_id(executionContext['node_id']);
    EXECUTION_LOG.push(node!.name);
    this.compute_count++;

    const result = new ExecutionResult(ExecCommand.CONTINUE);
    result.network_id = executionContext['network_id'];
    result.node_id = executionContext['node_id'];
    result.node_path = executionContext['node_path'];
    result.uuid = executionContext['uuid'];
    result.data_outputs['out'] = this.compute_count;
    return result;
  }
}

describe('TestNodeCooking', () => {
  beforeEach(() => {
    EXECUTION_LOG = [];
    NodeNetwork.deleteAllNodes();
  });

  test('test_cook_simple_dependency', async () => {
    /**
     * Structure: A -> B
     * cook_data_nodes(B) should trigger A then B.
     */
    const net = NodeNetwork.createRootNetwork('net_linear', 'NodeNetworkSystem');
    const nodeA = net.createNode('A', 'CookingTestNode');
    const nodeB = net.createNode('B', 'CookingTestNode');

    net.connectNodes('A', 'out', 'B', 'in');

    expect(net.graph.get_incoming_edges(nodeB.id, 'in').length).toBeGreaterThan(0);

    await new Executor(net.graph).cook_data_nodes(nodeB as any);

    expect(EXECUTION_LOG).toContain('A');
    expect(EXECUTION_LOG).toContain('B');
    expect(EXECUTION_LOG.indexOf('A')).toBeLessThan(EXECUTION_LOG.indexOf('B'));
  });

  test('test_cook_diamond_dependency', async () => {
    /**
     *        /--> B --\
     *  A              D
     *        \-> C --/
     * (fan-out A->B and A->C, but D can only have one incoming edge per port)
     */
    const net = NodeNetwork.createRootNetwork('net_diamond', 'NodeNetworkSystem');
    net.createNode('A', 'CookingTestNode');
    net.createNode('B', 'CookingTestNode');
    net.createNode('C', 'CookingTestNode');
    const nodeD = net.createNode('D', 'CookingTestNode');

    net.connectNodes('A', 'out', 'B', 'in');
    net.connectNodes('A', 'out', 'C', 'in');
    net.connectNodes('B', 'out', 'D', 'in');

    // Multiple edges to same port is not allowed
    expect(() => net.connectNodes('C', 'out', 'D', 'in')).toThrow();

    await new Executor(net.graph).cook_data_nodes(nodeD as any);

    expect(EXECUTION_LOG.length).toBe(3);
    expect(EXECUTION_LOG[0]).toBe('A');
    expect(EXECUTION_LOG[EXECUTION_LOG.length - 1]).toBe('D');
    expect(EXECUTION_LOG).toContain('B');
  });

  test('test_cook_fan_in', async () => {
    /**
     * A --\
     *      C
     * B --\  (B->C not allowed: same port already connected)
     */
    const net = NodeNetwork.createRootNetwork('net_fanin', 'NodeNetworkSystem');
    net.createNode('A', 'CookingTestNode');
    net.createNode('B', 'CookingTestNode');
    const nodeC = net.createNode('C', 'CookingTestNode');

    net.connectNodes('A', 'out', 'C', 'in');

    expect(() => net.connectNodes('B', 'out', 'C', 'in')).toThrow();

    await new Executor(net.graph).cook_data_nodes(nodeC as any);

    expect(EXECUTION_LOG).toContain('A');
    expect(EXECUTION_LOG[EXECUTION_LOG.length - 1]).toBe('C');
  });

  test('test_cook_disconnected', async () => {
    /**
     * A   B  (disconnected — cook B only)
     */
    const net = NodeNetwork.createRootNetwork('net_dis', 'NodeNetworkSystem');
    net.createNode('A', 'CookingTestNode');
    const nodeB = net.createNode('B', 'CookingTestNode');

    await new Executor(net.graph).cook_data_nodes(nodeB as any);

    expect(EXECUTION_LOG).toContain('B');
    expect(EXECUTION_LOG).not.toContain('A');
  });

  test('test_cook_chain_three', async () => {
    /**
     * A -> B -> C
     */
    const net = NodeNetwork.createRootNetwork('net_chain3', 'NodeNetworkSystem');
    net.createNode('A', 'CookingTestNode');
    net.createNode('B', 'CookingTestNode');
    const c = net.createNode('C', 'CookingTestNode');

    net.connectNodes('A', 'out', 'B', 'in');
    net.connectNodes('B', 'out', 'C', 'in');

    await new Executor(net.graph).cook_data_nodes(c as any);

    console.log('EXECUTION_LOG:', EXECUTION_LOG);
    expect(EXECUTION_LOG).toEqual(['A', 'B', 'C']);
  });
});
