/** Wire-format events received from the trace WebSocket stream (server → client). */
export type TraceEvent =
  | { type: 'EXEC_START';   networkId: string; rootNodeId: string; ts?: number }
  | { type: 'NODE_PENDING'; nodeId: string; networkId?: string; ts?: number }
  | { type: 'NODE_RUNNING'; nodeId: string; networkId?: string; ts?: number }
  | { type: 'NODE_DONE';    nodeId: string; networkId?: string;
      outputs?: Record<string, unknown>; durationMs: number; ts?: number }
  | { type: 'NODE_ERROR';   nodeId: string; networkId?: string;
      error: string; ts?: number }
  | { type: 'EDGE_ACTIVE';  fromNodeId: string; fromPort: string;
      toNodeId: string; toPort: string;
      value?: unknown; networkId?: string; ts?: number }
  | { type: 'STEP_PAUSE';   nodeId: string; networkId?: string; ts?: number }
  | { type: 'EXEC_DONE';   networkId: string; durationMs?: number; ts?: number }
  | { type: 'EXEC_ERROR';  networkId: string; error: string; ts?: number }
  // ── LangChain-specific ────────────────────────────────────────────────────
  /** Fired for each streamed token from LLMStreamNode */
  | { type: 'STREAM_CHUNK'; nodeId: string; chunk: string; accumulated: string; ts?: number }
  /** Fired for each tool call inside ToolAgentNode */
  | { type: 'AGENT_STEP';   nodeId: string; step: number; tool: string; input: string; output: string; ts?: number }
  /** Arbitrary key/value metadata (tokens, duration, dimensions, etc.) */
  | { type: 'NODE_DETAIL';  nodeId: string; detail: Record<string, unknown>; ts?: number };

/** Messages sent from client → server over the trace WebSocket. */
export type TraceCommand =
  | { type: 'STEP_RESUME' };
