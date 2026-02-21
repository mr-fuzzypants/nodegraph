import { IExecutionContext, IExecutionResult } from './Interface';
import { Node } from './Node';
import { Graph, Edge } from './GraphPrimitives';
import { PortDirection, PortFunction, NodeKind } from './Types';
import { NodePort } from './NodePort';

// ─────────────────────────────────────────────
// ExecCommand — mirrors Python ExecCommand enum
// ─────────────────────────────────────────────

export enum ExecCommand {
  CONTINUE = 'CONTINUE',
  WAIT = 'WAIT',
  LOOP_AGAIN = 'LOOP_AGAIN',
  COMPLETED = 'COMPLETED',
}

// ─────────────────────────────────────────────
// ExecutionCheckpoint
//
// A serialisable snapshot of the executor's full mid-run state.
// Saved after every successful batch so execution can be resumed from the
// last good position if a node throws, the server restarts, or the WS
// client disconnects during step mode.
// ─────────────────────────────────────────────

export interface ExecutionCheckpoint {
  /** The node that was passed to cook_flow_control_nodes as the entry point. */
  rootNodeId:     string;
  /** The network the execution belongs to. */
  networkId:      string;
  /** Nodes ready to execute in the next tick. */
  executionStack: string[];
  /** LIFO stack of loop re-entry node ids. Order matters — must be restored exactly. */
  deferredStack:  string[];
  /** Nodes waiting for dependencies, mapped to their remaining dep list. */
  pendingStack:   Record<string, string[]>;
  /** All node ids that have completed successfully so far. */
  completedNodes: string[];
  /**
   * Per-node internal state snapshots keyed by node id.
   * Populated by Node.serializeState() — includes port values AND any private
   * loop counters (e.g. ForLoopNode._loopIndex / _loopActive).
   */
  nodeStates:     Record<string, Record<string, unknown>>;
  /** Set when execution halted due to an error; null during normal progress. */
  failedNodeId:   string | null;
  failedError:    string | null;
  /** Wall-clock time when this snapshot was taken. */
  timestamp:      number;
}

// ─────────────────────────────────────────────
// ExecutionResult
// ─────────────────────────────────────────────

export class ExecutionResult implements IExecutionResult {
  command: ExecCommand;
  network_id: string;
  node_id: string;
  node_path: string;
  uuid: string;
  data_outputs: Record<string, any>;
  control_outputs: Record<string, any>;

  constructor(
    command: ExecCommand,
    controlOutputs?: Record<string, any> | null,
  ) {
    this.command = command;
    this.network_id = '';
    this.node_id = '';
    this.node_path = '';
    this.uuid = '';
    this.data_outputs = {};
    this.control_outputs = controlOutputs ?? {};
  }

  deserialize_result(node: Node): void {
    for (const [outputName, outputValue] of Object.entries(this.data_outputs)) {
      const outPort = node.outputs[outputName];
      if (outPort) {
        outPort.value = outputValue;
        outPort._isDirty = false;
      }
    }
    for (const [outputName, outputValue] of Object.entries(this.control_outputs)) {
      const outPort = node.outputs[outputName];
      if (outPort) {
        outPort.value = outputValue;
        outPort._isDirty = false;
      }
    }
    node.markClean();
  }
}

// ─────────────────────────────────────────────
// ExecutionContext
// ─────────────────────────────────────────────

export class ExecutionContext implements IExecutionContext {
  node: Node;
  network_id: string | null;
  data_inputs: Record<string, any>;
  data_outputs: Record<string, any>;

  constructor(node: Node) {
    this.node = node;
    this.network_id = node.network_id;
    this.data_inputs = {};
    this.data_outputs = {};
  }

  get_port_value(port: NodePort): any {
    return port.value;
  }

  to_dict(): Record<string, any> {
    const data_inputs: Record<string, any> = {};
    const control_inputs: Record<string, any> = {};

    for (const [portName, port] of Object.entries(this.node.inputs)) {
      if (port.isDataPort()) {
        data_inputs[portName] = this.get_port_value(port);
      } else if (port.isControlPort()) {
        control_inputs[portName] = this.get_port_value(port);
      }
    }

    return {
      uuid: this.node.uuid,
      network_id: this.network_id,
      node_id: this.node.id,
      node_path: this.node.path,
      data_inputs,
      control_inputs,
    };
  }

  from_dict(contextDict: Record<string, any>): void {
    for (const [portName, value] of Object.entries(
      contextDict['data_inputs'] ?? {},
    )) {
      const port = this.node.inputs[portName];
      if (port) {
        port.value = value;
        port._isDirty = false;
      }
    }
    for (const [portName, value] of Object.entries(
      contextDict['control_inputs'] ?? {},
    )) {
      const port = this.node.inputs[portName];
      if (port) {
        port.value = value;
        port._isDirty = false;
      }
    }
  }
}

// ─────────────────────────────────────────────
// PendingStackEntry / PendingStack
// ─────────────────────────────────────────────

class PendingStackEntry {
  node_id: string;
  dependencies: string[];

  constructor(nodeId: string) {
    this.node_id = nodeId;
    this.dependencies = [];
  }

  add_dependency(nodeId: string): void {
    if (!this.dependencies.includes(nodeId)) {
      this.dependencies.push(nodeId);
    }
  }

  remove_dependency(nodeId: string): void {
    const idx = this.dependencies.indexOf(nodeId);
    if (idx !== -1) this.dependencies.splice(idx, 1);
  }
}

class PendingStack {
  stack: Record<string, PendingStackEntry> = {};

  add_node(nodeId: string): void {
    if (!(nodeId in this.stack)) {
      this.stack[nodeId] = new PendingStackEntry(nodeId);
    }
  }

  add_dependency(nodeId: string, dependencyId: string): void {
    this.add_node(nodeId);
    this.stack[nodeId].add_dependency(dependencyId);
  }

  remove_dependency(nodeId: string, dependencyId: string): void {
    if (nodeId in this.stack) {
      this.stack[nodeId].remove_dependency(dependencyId);
      if (this.stack[nodeId].dependencies.length === 0) {
        delete this.stack[nodeId];
      }
    }
  }

  get_ready_nodes(): string[] {
    return Object.entries(this.stack)
      .filter(([, entry]) => entry.dependencies.length === 0)
      .map(([nodeId]) => nodeId);
  }
}

// ─────────────────────────────────────────────
// Executor
// ─────────────────────────────────────────────

export class Executor {
  graph: Graph;

  /**
   * Optional lifecycle hooks — set by the caller to observe per-node execution.
   * Called with the node id and name just before `compute()` is invoked.
   * May return a Promise — execution waits for it to resolve (enables step mode).
   */
  onBeforeNode?: (nodeId: string, nodeName: string) => void | Promise<void>;
  /**
   * Called with the node id, name, wall-clock duration, and (if the compute
   * threw) the error message.
   */
  onAfterNode?: (nodeId: string, nodeName: string, durationMs: number, error?: string) => void;
  /**
   * Called after every successfully completed batch and on error (with
   * failedNodeId / failedError set).  Consumers can persist the checkpoint to
   * enable execution resumption after a crash or disconnect.
   */
  onCheckpoint?: (checkpoint: ExecutionCheckpoint) => void;

  constructor(graph: Graph) {
    this.graph = graph;
  }

  async cook_flow_control_nodes(
    node: Node,
    executionStack: string[] = [],
    pendingStack: Record<string, string[]> = {},
    initialCheckpoint?: ExecutionCheckpoint,
  ): Promise<void> {
    // Deferred loop re-entries use a LIFO stack (pop from the end).
    //
    // Why LIFO and not FIFO?
    //   LOOP_AGAIN entries are pushed in temporal order: the outer loop fires
    //   first (tick 1) and pushes itself, then the inner loop fires (tick 2)
    //   and pushes itself. The innermost LOOP_AGAIN is therefore always at the
    //   TOP of the stack. pop() services the deepest pending re-entry first,
    //   which is exactly the correct nesting order:
    //
    //     OuterLoop iter 0 → deferredStack=[Outer], exec=[Inner]
    //     InnerLoop iter 0 → deferredStack=[Outer,Inner], exec=[Counter]
    //     Counter done, exec drains → pop() gives Inner  ← correct
    //     InnerLoop iter 1 → deferredStack=[Outer,Inner], exec=[Counter]
    //     Counter done       → pop() gives Inner again
    //     InnerLoop COMPLETED → deferredStack=[Outer]
    //     pop() gives Outer  → outer iter 1 starts fresh
    //
    // With FIFO (shift), Counter draining would give Outer from the front,
    // firing the second outer iteration before the inner loop finished.
    const deferredStack: string[] = [];
    const completedNodes: string[] = [];

    if (initialCheckpoint) {
      // ── Checkpoint restore ───────────────────────────────────────────────
      // Re-seed all stacks from the snapshot; the while loop below takes over
      // from there without re-calling build_flow_node_execution_stack.
      completedNodes.push(...initialCheckpoint.completedNodes);
      executionStack.push(...initialCheckpoint.executionStack);
      deferredStack.push(...initialCheckpoint.deferredStack);
      for (const [nid, deps] of Object.entries(initialCheckpoint.pendingStack)) {
        pendingStack[nid] = [...deps];
      }
      // Restore per-node internal state (loop counters, port values, …)
      for (const [nid, state] of Object.entries(initialCheckpoint.nodeStates)) {
        const n = this.graph.get_node_by_id(nid) as Node | null;
        n?.deserializeState(state);
      }
    } else {
      // ── Normal path ──────────────────────────────────────────────────────
      if (node.isFlowControlNode()) {
        this.build_flow_node_execution_stack(node, executionStack, pendingStack);
      }

      for (const nodeId of Object.keys(pendingStack)) {
        const deps = pendingStack[nodeId];
        if (deps.length === 0) {
          executionStack.push(nodeId);
          delete pendingStack[nodeId];
        }
      }
    }

    while (executionStack.length > 0 || deferredStack.length > 0) {
      // When the main stack empties, pop exactly ONE node from the deferred
      // stack (the most-recently-pushed = innermost loop re-entry).
      // That single node re-expands its body via build_flow_node_execution_stack
      // and runs to completion before popping the next deferred entry.
      if (executionStack.length === 0) {
        executionStack.push(deferredStack.pop()!);
      }

      // Collect entire current batch
      const batchIds = [...executionStack];
      executionStack.length = 0;

      if (batchIds.length === 0) continue;

      // Run batch in parallel
      const tasks = batchIds.map((nid) => this._execute_single_node(nid));
      let results: Awaited<ReturnType<typeof this._execute_single_node>>[];
      try {
        results = await Promise.all(tasks);
      } catch (batchErr: unknown) {
        // Emit an error checkpoint so consumers can resume from the last good state.
        if (this.onCheckpoint) {
          const nodeStates: Record<string, Record<string, unknown>> = {};
          for (const nid of completedNodes) {
            const n = this.graph.get_node_by_id(nid) as Node | null;
            if (n) nodeStates[nid] = n.serializeState();
          }
          const errMsg = batchErr instanceof Error ? batchErr.message : String(batchErr);
          this.onCheckpoint({
            rootNodeId:     node.id,
            networkId:      node.network_id ?? '',
            executionStack: [...batchIds],   // the batch that failed — re-run from here
            deferredStack:  [...deferredStack],
            pendingStack:   Object.fromEntries(
              Object.entries(pendingStack).map(([k, v]) => [k, [...v]])
            ),
            completedNodes: [...completedNodes],
            nodeStates,
            failedNodeId:   batchIds.length === 1 ? batchIds[0] : null,
            failedError:    errMsg,
            timestamp:      Date.now(),
          });
        }
        throw batchErr;
      }

      // Process results sequentially
      for (const [curNode, result] of results) {
        if (!curNode || !result) continue;

        // A. Deferred loop-back — push onto the LIFO stack.
        //    Inner loops push later than outer loops, so pop() always gives
        //    the innermost pending re-entry, ensuring inner completes before
        //    outer iterates again.
        if (result.command === ExecCommand.LOOP_AGAIN) {
          deferredStack.push(curNode.id);
        }

        // B. Propagate control outputs
        const connectedIds: string[] = [];
        for (const [controlName, controlValue] of Object.entries(
          result.control_outputs,
        )) {
          console.log(
            `     [3] Control Output from node ${curNode.name}: ${controlName} = ${controlValue}`,
          );
          const edges = this.graph.get_outgoing_edges(curNode.id, controlName);

          for (const edge of edges) {
            const toNode = this.graph.get_node_by_id(edge.to_node_id) as Node | null;
            if (toNode) {
              if (toNode.inputs[edge.to_port_name]) {
                toNode.inputs[edge.to_port_name].setValue(controlValue);
              } else if (toNode.outputs[edge.to_port_name]) {
                toNode.outputs[edge.to_port_name].setValue(controlValue);
              }
            }
          }

          const nextIds = edges
            .filter((e) => e.to_node_id !== curNode.network_id)
            .map((e) => e.to_node_id);
          connectedIds.push(...nextIds);
        }

        // C. Dependency resolution for next nodes
        for (const nextNodeId of connectedIds) {
          const nextNode = this.graph.get_node_by_id(nextNodeId) as Node | null;
          if (nextNode) {
            this.build_flow_node_execution_stack(
              nextNode,
              executionStack,
              pendingStack,
            );
          }
        }
      }

      // Promote ready nodes from pending → execution stack
      for (const nodeId of Object.keys(pendingStack)) {
        const deps = pendingStack[nodeId];
        for (const finishedId of batchIds) {
          const idx = deps.indexOf(finishedId);
          if (idx !== -1) deps.splice(idx, 1);
        }
        if (deps.length === 0) {
          executionStack.push(nodeId);
          delete pendingStack[nodeId];
        }
      }

      // ── Checkpoint ────────────────────────────────────────────────────────
      completedNodes.push(...batchIds);
      if (this.onCheckpoint) {
        const nodeStates: Record<string, Record<string, unknown>> = {};
        for (const nid of completedNodes) {
          const n = this.graph.get_node_by_id(nid) as Node | null;
          if (n) nodeStates[nid] = n.serializeState();
        }
        this.onCheckpoint({
          rootNodeId:     node.id,
          networkId:      node.network_id ?? '',
          executionStack: [...executionStack],
          deferredStack:  [...deferredStack],
          pendingStack:   Object.fromEntries(
            Object.entries(pendingStack).map(([k, v]) => [k, [...v]])
          ),
          completedNodes: [...completedNodes],
          nodeStates,
          failedNodeId:   null,
          failedError:    null,
          timestamp:      Date.now(),
        });
      }
      // ──────────────────────────────────────────────────────────────────────
    }

    for (const nodeId of Object.keys(pendingStack)) {
      const n = this.graph.get_node_by_id(nodeId) as Node | null;
      console.log(
        `Node '${n?.name ?? 'Unknown'}' (${nodeId}) still has dependencies: ${pendingStack[nodeId]}`,
      );
    }
    if (Object.keys(pendingStack).length !== 0) {
      throw new Error('Pending stack should be empty after cooking all flow control nodes');
    }
  }

  async _execute_single_node(
    curNodeId: string,
  ): Promise<[Node | null, ExecutionResult | null]> {
    const curNode = this.graph.get_node_by_id(curNodeId) as Node | null;
    if (!curNode) return [null, null];

    if (curNode.isNetwork()) {
      this.propogate_network_inputs_to_internal(curNode);
    }

    // Force cook upstream data dependencies (lazy load)
    for (const inputPort of curNode.get_input_data_ports()) {
      const upstreamNodes = this.get_upstream_nodes(inputPort);
      for (const upNode of upstreamNodes) {
        if ((upNode as Node).isDataNode()) {// && (upNode as Node).isDirty()) {
          await this._execute_single_node(upNode.id);
        }
      }
    }

    console.log(`.   [1] Cooking node: ${curNode.name} (${curNodeId})`);
    const context = new ExecutionContext(curNode).to_dict();
    console.log(
      `     [1.1] Execution Context for node: ${curNode.name}:`,
      context,
    );

    await this.onBeforeNode?.(curNodeId, curNode.name);

    const _t0 = Date.now();
    let result: ExecutionResult;
    try {
      result = await curNode.compute(context) as ExecutionResult;
    } catch (computeErr: unknown) {
      const errMsg = computeErr instanceof Error ? computeErr.message : String(computeErr);
      this.onAfterNode?.(curNodeId, curNode.name, Date.now() - _t0, errMsg);
      throw computeErr;
    }
    this.onAfterNode?.(curNodeId, curNode.name, Date.now() - _t0);

    result.deserialize_result(curNode);

    if (curNode.isNetwork()) {
      this.propogate_internal_node_outputs_to_network(curNode);
    }

    this.push_data_from_node(curNode);

    return [curNode, result];
  }

  build_flow_node_execution_stack(
    node: Node,
    executionStack: string[],
    pendingStack: Record<string, string[]>,
  ): void {
    if (!(node.id in pendingStack)) {
      pendingStack[node.id] = [];
    }

    for (const inputPort of node.get_input_ports()) {
      if (node.isNetwork()) {
        const downStreamNodes = this.get_downstream_nodes(inputPort);
        for (const downNode of downStreamNodes as Node[]) {
          if (downNode.isDirty()) {
            if (!(downNode.id in pendingStack)) {
              pendingStack[downNode.id] = [];
              if (!pendingStack[downNode.id].includes(node.id)) {
                pendingStack[downNode.id].push(node.id);
              }
            }
          }
        }
      }

      const upstreamNodes = this.get_upstream_nodes(inputPort) as Node[];

      for (const upNode of upstreamNodes) {
        if (!upNode.isDirty()) continue;

        if (upNode.isDataNode()) {
          if (!pendingStack[node.id].includes(upNode.id)) {
            pendingStack[node.id].push(upNode.id);
          }
          this.build_data_node_execution_stack(upNode, executionStack, pendingStack);
        }

        if (upNode.isNetwork()) {
          if (!pendingStack[node.id].includes(upNode.id)) {
            pendingStack[node.id].push(upNode.id);
          }
          this.build_flow_node_execution_stack(upNode, executionStack, pendingStack);
        }
      }
    }
  }

  build_data_node_execution_stack(
    node: Node,
    executionStack: string[],
    pendingStack: Record<string, string[]>,
  ): void {
    if (!(node.id in pendingStack)) {
      pendingStack[node.id] = [];
    }

    console.log(` 1. Building data node execution stack for node: ${node.name}`);

    for (const inputPort of node.get_input_data_ports()) {
      const upstreamNodes = this.get_upstream_nodes(inputPort) as Node[];
      for (const upNode of upstreamNodes) {
        if (!upNode.isDirty()) continue;

        if (upNode.isDataNode()) {
          if (!pendingStack[node.id].includes(upNode.id)) {
            pendingStack[node.id].push(upNode.id);
          }
          this.build_data_node_execution_stack(upNode, executionStack, pendingStack);
        }
      }
    }
  }

  propogate_network_inputs_to_internal(networkNode: Node): void {
    if (!networkNode.isNetwork()) {
      throw new Error('propogate_network_inputs() called on non-network node');
    }
    console.log(
      `=== PRE-Computing NodeNetwork Subnet: ${networkNode.name} with id: ${networkNode.id}`,
    );

    for (const [portName, port] of Object.entries(networkNode.inputs)) {
      if (port.isDataPort() && port.value !== null) {
        const edges = this.graph.get_outgoing_edges(networkNode.id, portName);
        for (const edge of edges) {
          const targetNode = this.graph.get_node_by_id(edge.to_node_id) as Node | null;
          if (targetNode) {
            if (edge.to_port_name in targetNode.inputs) {
              targetNode.inputs[edge.to_port_name].setValue(port.value);
            } else if (edge.to_port_name in targetNode.outputs) {
              targetNode.outputs[edge.to_port_name].setValue(port.value);
            }
          }
        }
      }
    }
  }

  propogate_internal_node_outputs_to_network(networkNode: Node): void {
    for (const [portName, port] of Object.entries(networkNode.outputs)) {
      const edges = this.graph.get_incoming_edges(networkNode.id, portName);
      for (const edge of edges) {
        const sourceNode = this.graph.get_node_by_id(edge.from_node_id) as Node | null;
        if (sourceNode) {
          let val: any = null;
          if (edge.from_port_name in sourceNode.outputs) {
            val = sourceNode.outputs[edge.from_port_name].value;
          } else if (edge.from_port_name in sourceNode.inputs) {
            val = sourceNode.inputs[edge.from_port_name].value;
          }
          if (val !== null) {
            port.value = val;
            port._isDirty = false;
          }
        }
      }
    }
  }

  /**
   * Fired for each edge that carries data during push_data_from_node.
   * Parameters: fromNodeId, fromPort, toNodeId, toPort.
   */
  onEdgeData?: (fromNodeId: string, fromPort: string, toNodeId: string, toPort: string) => void;

  push_data_from_node(node: Node): void {
    for (const [portName, port] of Object.entries(node.outputs)) {
      if (port.isDataPort() && port.value !== null) {
        const val = port.value;
        const outgoingEdges = this.graph.get_outgoing_edges(node.id, portName);
        for (const edge of outgoingEdges) {
          const targetNode = this.graph.get_node_by_id(edge.to_node_id) as Node | null;
          if (targetNode) {
            if (edge.to_port_name in targetNode.inputs) {
              targetNode.inputs[edge.to_port_name].setValue(val);
            } else if (edge.to_port_name in targetNode.outputs) {
              targetNode.outputs[edge.to_port_name].setValue(val);
            }
            this.onEdgeData?.(node.id, portName, edge.to_node_id, edge.to_port_name);
          }
        }
      }
    }
  }

  get_upstream_nodes(port: any): Node[] {
    const incomingEdges = this.graph.get_incoming_edges(port.node_id, port.port_name);
    const upstreamNodes: Node[] = [];
    for (const edge of incomingEdges) {
      const srcNode = this.graph.get_node_by_id(edge.from_node_id) as Node | null;
      if (srcNode) upstreamNodes.push(srcNode);
    }
    return upstreamNodes;
  }

  get_downstream_nodes(port: any): Node[] {
    const outgoingEdges = this.graph.get_outgoing_edges(port.node_id, port.port_name);
    const downstreamNodes: Node[] = [];
    for (const edge of outgoingEdges) {
      const destNode = this.graph.get_node_by_id(edge.to_node_id) as Node | null;
      if (destNode && !downstreamNodes.includes(destNode)) {
        downstreamNodes.push(destNode);
      }
    }
    return downstreamNodes;
  }

  /** Cook data nodes — mirrors Python Executor.cook_data_nodes */
  async cook_data_nodes(node: Node): Promise<void> {
    const executionStack: string[] = [];
    const pendingStack: Record<string, string[]> = {};

    if (node.isDataNode()) {
      this.build_data_node_execution_stack(node, executionStack, pendingStack);
    }

    console.log('Pending Stack:', pendingStack);
    console.log('Initial Execution Stack:', executionStack);

    // Move nodes with no deps to execution stack
    for (const nodeId of Object.keys(pendingStack)) {
      const deps = pendingStack[nodeId];
      if (deps.length === 0) {
        executionStack.push(nodeId);
        delete pendingStack[nodeId];
      }
    }

    while (executionStack.length > 0) {
      console.log('Execution Stack:', executionStack);
      const curNodeId = executionStack.shift()!;
      const curNode = this.graph.get_node_by_id(curNodeId) as Node | null;

      if (curNode && curNode.isDataNode()) {
        console.log(`.   Cooking node: ${curNode.name} ${curNodeId}`);

        await this.onBeforeNode?.(curNodeId, curNode.name);

        const context = new ExecutionContext(curNode).to_dict();
        console.log('.       Context:', context);
        const _t0 = Date.now();
        let result: ExecutionResult;
        try {
          result = await curNode.compute(context) as ExecutionResult;
        } catch (computeErr: unknown) {
          const errMsg = computeErr instanceof Error ? computeErr.message : String(computeErr);
          this.onAfterNode?.(curNodeId, curNode.name, Date.now() - _t0, errMsg);
          throw computeErr;
        }
        this.onAfterNode?.(curNodeId, curNode.name, Date.now() - _t0);
        console.log('.       Result:', result.command, result.data_outputs);

        result.deserialize_result(curNode);
      }

      // Update pending stack
      for (const nodeId of Object.keys(pendingStack)) {
        const deps = pendingStack[nodeId];
        const idx = deps.indexOf(curNodeId);
        if (idx !== -1) {
          deps.splice(idx, 1);
          if (deps.length === 0) {
            executionStack.push(nodeId);
            delete pendingStack[nodeId];
          }
        }
      }
    }
  }
}
