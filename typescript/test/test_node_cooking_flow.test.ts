/**
 * Port of python/test/test_node_cooking_flow.py
 * Tests flow-control node execution order, data–flow mixing,
 * subnetwork tunneling, and nested subnetwork hierarchies.
 */
import { Node } from '../src/core/Node';
import { NodeNetwork } from '../src/core/NodeNetwork';
import {
  ExecCommand,
  ExecutionResult,
  ExecutionContext,
  Executor,
} from '../src/core/Executor';
import {
  InputControlPort,
  OutputControlPort,
  InputDataPort,
  OutputDataPort,
} from '../src/core/NodePort';
import { ValueType } from '../src/core/Types';

let EXECUTION_LOG: string[] = [];

// ──────────────────────────────────────
// Shared test node registrations
// ──────────────────────────────────────

@Node.register('FlowTestNode')
class FlowTestNode extends Node {
  constructor(id: string, type: string = 'FlowTestNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.is_flow_control_node = true;
    this.inputs['exec'] = new InputControlPort(this.id, 'exec');
    this.outputs['next'] = new OutputControlPort(this.id, 'next');
    this.inputs['data_in'] = new InputDataPort(this.id, 'data_in', ValueType.INT);
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    EXECUTION_LOG.push(this.name);
    console.log(`COMPUTING FLOW NODE: ${this.name}`);

    const result = new ExecutionResult(ExecCommand.CONTINUE);
    result.network_id = executionContext['network_id'];
    result.node_id = executionContext['node_id'];
    result.node_path = executionContext['node_path'];
    result.uuid = executionContext['uuid'];
    result.control_outputs['next'] = true;
    return result;
  }
}

@Node.register('DataTestNode')
class DataTestNode extends Node {
  constructor(id: string, type: string = 'DataTestNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.is_flow_control_node = false;
    this.outputs['out'] = new OutputDataPort(this.id, 'out', ValueType.INT);
    this.outputs['out'].value = 100;
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    EXECUTION_LOG.push(this.name);
    console.log(`COMPUTING DATA NODE: ${this.name}`);

    const result = new ExecutionResult(ExecCommand.CONTINUE);
    if (executionContext) {
      result.network_id = executionContext['network_id'];
      result.node_id = executionContext['node_id'];
      result.node_path = executionContext['node_path'];
      result.uuid = executionContext['uuid'];
    }
    result.data_outputs['out'] = this.outputs['out'].value;
    return result;
  }
}

@Node.register('MathAddNode')
class MathAddNode extends Node {
  constructor(id: string, type: string = 'MathAddNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.is_flow_control_node = false;
    this.inputs['a'] = new InputDataPort(this.id, 'a', ValueType.INT);
    this.inputs['b'] = new InputDataPort(this.id, 'b', ValueType.INT);
    this.outputs['sum'] = new OutputDataPort(this.id, 'sum', ValueType.INT);
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    const valA = this.inputs['a'].value ?? 0;
    const valB = this.inputs['b'].value ?? 0;
    const res = valA + valB;
    EXECUTION_LOG.push(this.name);

    const result = new ExecutionResult(ExecCommand.CONTINUE);
    result.data_outputs['sum'] = res;
    return result;
  }
}

@NodeNetwork.register('MockSubnetNode')
class MockSubnetNode extends NodeNetwork {
  constructor(
    id: string,
    type: string = 'MockSubnetNode',
    networkId: string | null = null,
    graph: any = null,
  ) {
    super(id, type, networkId, graph);
    this.is_flow_control_node = true;
    (this as any).cooking_internally = false;
  }

  async compute(executionContext?: any): Promise<ExecutionResult> {
    EXECUTION_LOG.push(`Subnet:${this.name}`);
    return await super.compute(executionContext);
  }
}

// ──────────────────────────────────────
// Tests
// ──────────────────────────────────────
describe('TestNodeCookingFlow', () => {
  beforeEach(() => {
    EXECUTION_LOG = [];
  });

  test('test_flow_linear', async () => {
    /**
     * Start(F) -> Middle(F) -> End(F)
     */
    const net = NodeNetwork.createRootNetwork('net_flow_linear', 'NodeNetworkSystem');
    const n1 = net.createNode('Start', 'FlowTestNode');
    net.createNode('Middle', 'FlowTestNode');
    net.createNode('End', 'FlowTestNode');

    net.connectNodesByPath('/net_flow_linear:Start', 'next', '/net_flow_linear:Middle', 'exec');
    net.connectNodesByPath('/net_flow_linear:Middle', 'next', '/net_flow_linear:End', 'exec');

    await new Executor(net.graph).cook_flow_control_nodes(n1 as any);

    expect(EXECUTION_LOG).toEqual(['Start', 'Middle', 'End']);
  });

  test('test_flow_branch', async () => {
    /**
     *      /-> B(F)
     * A(F)
     *      \-> C(F)
     */
    const net = NodeNetwork.createRootNetwork('net_flow_branch', 'NodeNetworkSystem');
    const nA = net.createNode('A', 'FlowTestNode');
    net.createNode('B', 'FlowTestNode');
    net.createNode('C', 'FlowTestNode');

    net.connectNodesByPath('/net_flow_branch:A', 'next', '/net_flow_branch:B', 'exec');
    net.connectNodesByPath('/net_flow_branch:A', 'next', '/net_flow_branch:C', 'exec');

    await new Executor(net.graph).cook_flow_control_nodes(nA as any);

    expect(EXECUTION_LOG).toContain('A');
    expect(EXECUTION_LOG).toContain('B');
    expect(EXECUTION_LOG).toContain('C');
    expect(EXECUTION_LOG[0]).toBe('A');
    expect(EXECUTION_LOG.length).toBe(3);
  });

  test('test_mixed_data_flow', async () => {
    /**
     * [DataNode]
     *     | (val=100)
     *     v
     * [FlowStart] -> [FlowConsumer]
     */
    const net = NodeNetwork.createRootNetwork('net_mixed', 'NodeNetworkSystem');
    const flowStart = net.createNode('Start', 'FlowTestNode');
    net.createNode('Consumer', 'FlowTestNode');
    net.createNode('Provider', 'DataTestNode');

    net.connectNodesByPath('/net_mixed:Start', 'next', '/net_mixed:Consumer', 'exec');
    net.connectNodesByPath('/net_mixed:Provider', 'out', '/net_mixed:Consumer', 'data_in');

    await new Executor(net.graph).cook_flow_control_nodes(flowStart as any);

    expect(EXECUTION_LOG).toContain('Start');
    expect(EXECUTION_LOG).toContain('Consumer');
    expect(EXECUTION_LOG).toContain('Provider');
  });

  test('test_subnetwork_tunneling', async () => {
    /**
     * [ExternalData(123)] -> [Subnet.tunnel_data] -> [InternalFlow]
     */
    const net = NodeNetwork.createRootNetwork('root', 'NodeNetworkSystem');
    const subnetStop = net.createNetwork('subnet_stop', 'NodeNetworkSystem');

    const extData = net.createNode('ExtData', 'DataTestNode') as any;
    extData.outputs['out'].value = 123;

    subnetStop.add_data_input_port('tunnel_data');
    subnetStop.add_control_input_port('tunnel_exec');

    const internalFlow = subnetStop.createNode('InternalFlow', 'FlowTestNode');

    net.connectNodesByPath('/root:ExtData', 'out', '/root/subnet_stop', 'tunnel_data');
    subnetStop.connectNodesByPath(
      '/root/subnet_stop',
      'tunnel_data',
      '/root/subnet_stop:InternalFlow',
      'data_in',
    );
    subnetStop.connectNodesByPath(
      '/root/subnet_stop',
      'tunnel_exec',
      '/root/subnet_stop:InternalFlow',
      'exec',
    );

    await new Executor(net.graph).cook_flow_control_nodes(internalFlow as any);

    console.log('EXECUTION LOG:', EXECUTION_LOG);
    expect(EXECUTION_LOG).toContain('InternalFlow');
    expect(EXECUTION_LOG).toContain('ExtData');
  });

  test('test_nested_subnetwork_flow', async () => {
    /**
     * Root -> [Subnet A] -> [Subnet B] -> FlowNode
     */
    const root = NodeNetwork.createRootNetwork('root', 'NodeNetworkSystem');
    const subnetA = root.createNetwork('A', 'NodeNetworkSystem');
    const subnetB = subnetA.createNetwork('B', 'NodeNetworkSystem');

    const leafNode = subnetB.createNode('Leaf', 'FlowTestNode');

    subnetA.add_control_input_port('exec');
    subnetB.add_control_input_port('exec');

    root.connectNodesByPath('/root/A', 'exec', '/root/A/B', 'exec');
    root.connectNodesByPath('/root/A/B', 'exec', '/root/A/B:Leaf', 'exec');

    await new Executor(root.graph).cook_flow_control_nodes(leafNode as any);

    expect(EXECUTION_LOG).toContain('Leaf');
  });
});
