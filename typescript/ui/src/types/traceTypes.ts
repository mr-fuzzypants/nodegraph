/** Wire-format events received from the trace WebSocket stream (server → client). */
export type TraceEvent =
  | { type: 'EXEC_START';   networkId: string; rootNodeId: string; runId?: string; ts?: number }
  | { type: 'NODE_PENDING'; nodeId: string; networkId?: string; ts?: number }
  | { type: 'NODE_RUNNING'; nodeId: string; networkId?: string; nodeName?: string; nodePath?: string; ts?: number }
  | { type: 'NODE_DONE';    nodeId: string; networkId?: string;
      outputs?: Record<string, unknown>; durationMs: number; nodeName?: string; nodePath?: string; ts?: number }
  | { type: 'NODE_ERROR';   nodeId: string; networkId?: string;
      nodeName?: string; nodePath?: string; durationMs?: number; error: string; ts?: number }
  | { type: 'NODE_PROGRESS'; nodeId: string; progress: number; message?: string; ts?: number }
  | { type: 'NODE_STATUS';   nodeId: string; status: string; ts?: number }
  | { type: 'EDGE_ACTIVE';  fromNodeId: string; fromPort: string;
      toNodeId: string; toPort: string;
      value?: unknown; networkId?: string; ts?: number }
  | { type: 'STEP_PAUSE';   nodeId: string; networkId?: string; ts?: number }
  | { type: 'EXEC_DONE';   networkId: string; durationMs?: number; ts?: number }
  | { type: 'EXEC_ERROR';  networkId: string; runId?: string; error: string; ts?: number }
  // ── LangChain-specific ────────────────────────────────────────────────────
  /** Fired for each streamed token from LLMStreamNode */
  | { type: 'STREAM_CHUNK'; nodeId: string; chunk: string; accumulated: string; ts?: number }
  /** Fired for each tool call inside ToolAgentNode */
  | { type: 'AGENT_STEP';   nodeId: string; step: number; tool: string; input: string; output: string; ts?: number }
  /** Arbitrary key/value metadata (tokens, duration, dimensions, etc.) */
  | { type: 'NODE_DETAIL';  nodeId: string; detail: Record<string, unknown>; ts?: number }
  /** Fired by HumanInputNode when it is suspended waiting for a human response. */
  | { type: 'HUMAN_INPUT_REQUIRED'; nodeId: string; prompt: string; workflowId?: string | null; ts?: number };

/** Messages sent from client → server over the trace WebSocket. */
export type TraceCommand =
  | { type: 'STEP_RESUME' };
