/**
 * Port of python/test/test_node_network.py
 * Tests NodeNetwork creation, node factory, port tunneling, connect/delete, 
 * and upstream/downstream graph traversal.
 */
import { Node } from '../src/core/Node';
import { NodeNetwork } from '../src/core/NodeNetwork';
import { ExecCommand, ExecutionResult, ExecutionContext } from '../src/core/Executor';
import { ValueType, PortDirection, PortFunction } from '../src/core/Types';
import { Edge } from '../src/core/GraphPrimitives';
import {
  NodePort,
  OutputControlPort,
  InputControlPort,
  OutputDataPort,
  InputDataPort,
} from '../src/core/NodePort';

// ──────────────────────────────────────
// Mock node
// ──────────────────────────────────────
@Node.register('MockNode')
class MockNode extends Node {
  computed: boolean;

  constructor(id: string, type: string = 'MockNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.computed = false;

    this.inputs['in'] = new InputControlPort(this.id, 'in');
    this.outputs['out'] = new OutputControlPort(this.id, 'out');
    this.inputs['data_in'] = new InputDataPort(this.id, 'data_in', ValueType.INT);
    this.outputs['data_out'] = new OutputDataPort(this.id, 'data_out', ValueType.INT);
  }

  async compute(): Promise<ExecutionResult> {
    this.computed = true;
    return new ExecutionResult(ExecCommand.CONTINUE);
  }
}

// ──────────────────────────────────────
// Tests
// ──────────────────────────────────────
describe('TestNodeNetwork', () => {
  beforeEach(() => {
    NodeNetwork.deleteAllNodes();
  });

  afterEach(() => {
    NodeNetwork.deleteAllNodes();
  });

  test('test_network_creation', () => {
    const net = NodeNetwork.createRootNetwork('net1', 'NodeNetworkSystem');
    expect(net.name).toBe('net1');
    expect(net.isNetwork()).toBe(true);
    expect(net.isRootNetwork()).toBe(true);
    // A network is also a node in its own graph
    expect(net.graph.nodes.size).toBe(1);
  });

  test('test_create_node_factory', () => {
    const net = NodeNetwork.createRootNetwork('net1', 'NodeNetworkSystem');

    const node = net.createNode('n1', 'MockNode');
    expect(node.name).toBe('n1');
    expect(node.type).toBe('MockNode');
    expect(net.graph.get_node_by_name('n1')).toBe(node);

    // Duplicate ID protection
    expect(() => net.createNode('n1', 'MockNode')).toThrow();
  });

  test('test_create_subnetwork', () => {
    const root = NodeNetwork.createRootNetwork('root', 'NodeNetworkSystem');
    const subnet = root.createNetwork('subnet1', 'NodeNetworkSystem');

    expect(subnet.name).toBe('subnet1');
    expect(subnet.network_id).toBe(root.id);
    expect(root.graph.get_node_by_name('subnet1')).toBe(subnet);
    expect(subnet.isSubnetwork()).toBe(true);
    expect(subnet.isRootNetwork()).toBe(false);

    // Deep nesting
    const subsubnet = subnet.createNetwork('deep_net', 'NodeNetworkSystem');
    expect(subsubnet.network_id).toBe(subnet.id);
  });

  test('test_add_network_ports', () => {
    const net = NodeNetwork.createRootNetwork('net1', 'NodeNetworkSystem');

    const inCtrl = net.add_control_input_port('start');
    const inData = net.add_data_input_port('param');

    expect('start' in net.inputs).toBe(true);
    expect('param' in net.inputs).toBe(true);

    expect(inCtrl.port_name).toBe('start');
    expect(inCtrl.function).toBe(PortFunction.CONTROL);
    expect(inCtrl.direction).toBe(PortDirection.INPUT_OUTPUT);

    expect(inData.port_name).toBe('param');
    expect(inData.function).toBe(PortFunction.DATA);
    expect(inData.direction).toBe(PortDirection.INPUT_OUTPUT);
  });

  test('test_connect_nodes_internal', () => {
    const net = NodeNetwork.createRootNetwork('net_test', 'NodeNetworkSystem');
    const nodeA = net.createNode('A', 'MockNode');
    const nodeB = net.createNode('B', 'MockNode');

    const edge = net.connectNodes('A', 'out', 'B', 'in');

    expect(edge).toBeInstanceOf(Edge);
    expect(net.graph.get_node_by_id(edge.from_node_id)!.name).toBe('A');
    expect(edge.from_port_name).toBe('out');
    expect(net.graph.get_node_by_id(edge.to_node_id)!.name).toBe('B');
    expect(edge.to_port_name).toBe('in');

    const edges = net.graph.get_outgoing_edges(nodeA.id, 'out');
    expect(edges.length).toBe(1);
    expect(edges[0]).toEqual(edge);

    const edgesIn = net.graph.get_incoming_edges(nodeB.id, 'in');
    expect(edgesIn.length).toBe(1);
  });

  test('test_connect_node_not_found', () => {
    const net = NodeNetwork.createRootNetwork('net_err', 'NodeNetworkSystem');

    expect(() => net.connectNodes('Missing1', 'out', 'Missing2', 'in')).toThrow(
      /does not exist/,
    );
  });

  test('test_connect_network_input_to_internal', () => {
    const net = NodeNetwork.createRootNetwork('net_tunnel', 'NodeNetworkSystem');
    const internalNode = net.createNode('inner', 'MockNode');

    net.add_control_input_port('sys_start');
    net.connect_network_input_to('sys_start', internalNode as any, 'in');

    const edges = net.graph.get_outgoing_edges(net.id, 'sys_start');
    expect(edges.length).toBe(1);
    const edge = edges[0];
    expect(edge.from_node_id).toBe(net.id);
    expect(net.graph.get_node_by_id(edge.to_node_id)!.name).toBe('inner');
  });

  test('test_delete_node', () => {
    const net = NodeNetwork.createRootNetwork('root_net', 'NodeNetworkSystem');
    net.createNode('A', 'MockNode');
    net.createNode('B', 'MockNode');
    net.connectNodes('A', 'out', 'B', 'in');

    expect(net.graph.edges.length).toBe(1);

    net.deleteNode('A');

    const networkPath = net.graph.get_path(net.id);
    expect(net.graph.get_node_by_path(`${networkPath}:A`)).toBeNull();

    // Connection cleanup
    expect(net.graph.edges.length).toBe(0);

    expect(() => net.deleteNode('A')).toThrow();
  });

  test('test_get_downstream_ports', () => {
    /**
     * [n1 (data_out)] -> [n2 (data_in)]
     *                 -> [n3 (data_in)]
     */
    const net = NodeNetwork.createRootNetwork('net_downstream', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');
    const n3 = net.createNode('n3', 'MockNode');

    net.connectNodes('n1', 'data_out', 'n2', 'data_in');
    net.connectNodes('n1', 'data_out', 'n3', 'data_in');

    const srcPort = (n1 as any).outputs['data_out'];
    const downstream = net.graph.get_downstream_ports(srcPort);

    expect(downstream.length).toBe(2);
    expect(downstream).toContain((n2 as any).inputs['data_in']);
    expect(downstream).toContain((n3 as any).inputs['data_in']);
  });

  test('test_get_downstream_ports_iterative', () => {
    const net = NodeNetwork.createRootNetwork('net_iterative', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');

    net.connectNodes('n1', 'data_out', 'n2', 'data_in');

    const srcPort = (n1 as any).outputs['data_out'];
    const ports = net.graph.get_downstream_ports(srcPort);
    expect(ports.length).toBe(1);
    expect(ports[0]).toBe((n2 as any).inputs['data_in']);
  });

  test('test_get_upstream_ports', () => {
    const net = NodeNetwork.createRootNetwork('net_upstream', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');

    net.connectNodes('n1', 'data_out', 'n2', 'data_in');

    const targetPort = (n2 as any).inputs['data_in'];
    const upstream = net.graph.get_upstream_ports(targetPort);

    expect(upstream.length).toBe(1);
    expect(upstream[0]).toBe((n1 as any).outputs['data_out']);
  });

  test('test_get_downstream_ports_tunneling', () => {
    /**
     * [n1] -> [relay.io_port] -> [n2]
     * Testing tunneling through an INPUT_OUTPUT port.
     */
    const net = NodeNetwork.createRootNetwork('root', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');

    const relayNode = net.createNetwork('relay', 'NodeNetworkSystem');
    relayNode.add_data_input_port('io_port');

    // Edges manually: n1 -> relay, relay -> n2
    net.graph.add_edge(n1.id, 'data_out', relayNode.id, 'io_port');
    net.graph.add_edge(relayNode.id, 'io_port', n2.id, 'data_in');

    const srcPort = (n1 as any).outputs['data_out'];
    const downstream = net.graph.get_downstream_ports(srcPort);

    expect(downstream.length).toBe(1);
    expect(downstream[0]).toBe((n2 as any).inputs['data_in']);

    // With IO ports included
    const downstreamAll = net.graph.get_downstream_ports(srcPort, true);
    expect(downstreamAll.length).toBe(2);
    expect(downstreamAll).toContain((relayNode as any).inputs['io_port']);
  });

  test('test_get_upstream_ports_tunneling', () => {
    const net = NodeNetwork.createRootNetwork('root_up', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');

    const relayNode = net.createNetwork('relay', 'NodeNetworkSystem');
    relayNode.add_data_input_port('io_port');

    net.graph.add_edge(n1.id, 'data_out', relayNode.id, 'io_port');
    net.graph.add_edge(relayNode.id, 'io_port', n2.id, 'data_in');

    const targetPort = (n2 as any).inputs['data_in'];
    const upstream = net.graph.get_upstream_ports(targetPort);

    expect(upstream.length).toBe(1);
    expect(upstream[0]).toBe((n1 as any).outputs['data_out']);
  });

  test('test_get_input_port_value', () => {
    const net = NodeNetwork.createRootNetwork('net_val', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');

    net.graph.add_edge(n1.id, 'data_out', n2.id, 'data_in');

    (n1 as any).outputs['data_out'].value = 99;

    const targetPort = (n2 as any).inputs['data_in'] as NodePort;
    targetPort._isDirty = true;

    const val = net.get_input_port_value(targetPort);

    expect(val).toBe(99);
    expect(targetPort.value).toBe(99);
    expect(targetPort.isDirty()).toBe(false);
  });

  test('test_get_input_port_value_multiple_drivers', () => {
    /**
     * Two sources drive one input — last one wins (LIFO/stack pop).
     */
    const net = NodeNetwork.createRootNetwork('net_multi', 'NodeNetworkSystem');
    const n1 = net.createNode('n1', 'MockNode');
    const n2 = net.createNode('n2', 'MockNode');
    const n3 = net.createNode('n3', 'MockNode');

    net.graph.add_edge(n1.id, 'data_out', n3.id, 'data_in');
    net.graph.add_edge(n2.id, 'data_out', n3.id, 'data_in');

    (n1 as any).outputs['data_out'].value = 10;
    (n2 as any).outputs['data_out'].value = 20;

    const targetPort = (n3 as any).inputs['data_in'] as NodePort;
    targetPort._isDirty = true;

    const val = net.get_input_port_value(targetPort);

    // n2 wins because it was added last (pop() from end of array)
    expect(val).toBe(20);
    expect(targetPort.value).toBe(20);
    // Back-propagate: n1's output overwritten
    expect((n1 as any).outputs['data_out'].value).toBe(20);
  });
});
