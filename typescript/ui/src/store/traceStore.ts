import { create } from 'zustand';
import type { TraceEvent } from '../types/traceTypes';

// ── Types ─────────────────────────────────────────────────────────────────────

export type NodeTraceState = 'idle' | 'pending' | 'running' | 'paused' | 'done' | 'error';

export interface NodeTraceInfo {
  state: NodeTraceState;
  durationMs?: number;
  error?: string;
  // LangChain extras
  streamBuffer?: string;      // live-accumulating text from LLMStreamNode
  agentSteps?: AgentStep[];   // tool calls from ToolAgentNode
  detail?: Record<string, unknown>;  // tokens, dimensions, durationMs, etc.
}

export interface AgentStep {
  step:   number;
  tool:   string;
  input:  string;
  output: string;
}

export interface ActiveEdge {
  key: string;          // `${fromNodeId}:${fromPort}->${toNodeId}:${toPort}`
  fromNodeId: string;
  fromPort: string;
  toNodeId: string;
  toPort: string;
  expiresAt: number;    // Date.now() + TTL
}

const MAX_AGENT_STEPS = 100;

interface TraceStore {
  /** Per-node trace state, keyed by nodeId */
  nodeStates: Record<string, NodeTraceInfo>;
  /** Edges currently highlighted as "active" */
  activeEdges: ActiveEdge[];
  isRunning: boolean;
  lastError: string | null;
  stepModeEnabled: boolean;
  isPaused: boolean;
  pausedAtNodeId: string | null;

  applyEvent: (e: TraceEvent) => void;
  reset: () => void;
  /** Clear all trace state — call before starting a new execution run */
  clearTrace: () => void;
  setStepMode: (enabled: boolean) => void;
  resume: () => void;
}

const EDGE_TTL_MS = 1200;

export const useTraceStore = create<TraceStore>((set) => {
  // Periodically prune expired edges so they don't pile up during long loop runs.
  // Only triggers a state update when there are actually stale edges to remove.
  setInterval(() => {
    const now = Date.now();
    useTraceStore.setState((s) => {
      if (s.activeEdges.length === 0 || s.activeEdges.every((e) => e.expiresAt > now)) return s;
      return { activeEdges: s.activeEdges.filter((e) => e.expiresAt > now) };
    });
  }, 500);

  return {
  nodeStates:  {},
  activeEdges: [],
  isRunning:   false,
  lastError:   null,
  stepModeEnabled: false,
  isPaused:    false,
  pausedAtNodeId: null,

  setStepMode: (enabled) => set({ stepModeEnabled: enabled }),
  resume: () => set({ isPaused: false, pausedAtNodeId: null }),

  reset: () => set({ nodeStates: {}, activeEdges: [], isRunning: false, lastError: null, isPaused: false, pausedAtNodeId: null }),

  clearTrace: () => set({ nodeStates: {}, activeEdges: [], lastError: null, isPaused: false, pausedAtNodeId: null }),

  applyEvent: (e) =>
    set((s) => {
      const now = Date.now();

      switch (e.type) {
        case 'EXEC_START':
          return { isRunning: true, lastError: null, nodeStates: {}, activeEdges: [], isPaused: false, pausedAtNodeId: null };

        case 'STEP_PAUSE':
          return {
            isPaused: true,
            pausedAtNodeId: e.nodeId,
            nodeStates: { ...s.nodeStates, [e.nodeId]: { state: 'paused' } },
          };

        case 'NODE_PENDING':
          return { nodeStates: { ...s.nodeStates, [e.nodeId]: { state: 'pending' } } };

        case 'NODE_RUNNING':
          return { isPaused: false, pausedAtNodeId: null, nodeStates: { ...s.nodeStates, [e.nodeId]: { state: 'running' } } };

        case 'NODE_DONE':
          return {
            nodeStates: {
              ...s.nodeStates,
              [e.nodeId]: { state: 'done', durationMs: e.durationMs },
            },
          };

        case 'NODE_ERROR':
          return {
            nodeStates: {
              ...s.nodeStates,
              [e.nodeId]: { state: 'error', error: e.error },
            },
          };

        case 'EDGE_ACTIVE': {
          const key = `${e.fromNodeId}:${e.fromPort}->${e.toNodeId}:${e.toPort}`;
          const fresh: ActiveEdge = {
            key, fromNodeId: e.fromNodeId, fromPort: e.fromPort,
            toNodeId: e.toNodeId, toPort: e.toPort,
            expiresAt: now + EDGE_TTL_MS,
          };
          return {
            activeEdges: [
              ...s.activeEdges.filter((a) => a.expiresAt > now && a.key !== key),
              fresh,
            ],
          };
        }

        case 'EXEC_DONE':
          return { isRunning: false, isPaused: false, pausedAtNodeId: null };

        case 'EXEC_ERROR':
          return { isRunning: false, isPaused: false, pausedAtNodeId: null, lastError: e.error };

        // ── LangChain events ────────────────────────────────────────────────

        case 'STREAM_CHUNK': {
          const prev = s.nodeStates[e.nodeId] ?? { state: 'running' as NodeTraceState };
          return {
            nodeStates: {
              ...s.nodeStates,
              [e.nodeId]: { ...prev, streamBuffer: e.accumulated },
            },
          };
        }

        case 'AGENT_STEP': {
          const prev  = s.nodeStates[e.nodeId] ?? { state: 'running' as NodeTraceState };
          const steps = [...(prev.agentSteps ?? []), {
            step: e.step, tool: e.tool, input: e.input, output: e.output,
          }].slice(-MAX_AGENT_STEPS);
          return {
            nodeStates: {
              ...s.nodeStates,
              [e.nodeId]: { ...prev, agentSteps: steps },
            },
          };
        }

        case 'NODE_DETAIL': {
          const prev = s.nodeStates[e.nodeId] ?? { state: 'running' as NodeTraceState };
          return {
            nodeStates: {
              ...s.nodeStates,
              [e.nodeId]: { ...prev, detail: e.detail },
            },
          };
        }

        default:
          return {};
      }
    }),
  };
});
