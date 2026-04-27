import { useEffect, useRef, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import type { TraceEvent } from '../types/traceTypes';
import { useInfoLogStore } from '../store/infoLogStore';

const SOCKET_URL = 'http://localhost:3001';

function logSocket(status: 'pending' | 'success' | 'error' | 'info', message: string) {
  useInfoLogStore.getState().addEntry({ kind: 'websocket', status, message });
}

function formatNodeLabel(event: Extract<TraceEvent, { nodeId: string }>): string {
  const name = 'nodeName' in event && event.nodeName ? event.nodeName : event.nodeId;
  const path = 'nodePath' in event && event.nodePath ? ` path=${event.nodePath}` : '';
  return `${name} (${event.nodeId})${path}`;
}

function summarizeTraceEvent(event: TraceEvent): string {
  switch (event.type) {
    case 'EXEC_START':
      return `trace ${event.type} network=${event.networkId} root=${event.rootNodeId}`;
    case 'EXEC_DONE':
      return `trace ${event.type} network=${event.networkId}${event.durationMs ? ` ${event.durationMs}ms` : ''}`;
    case 'EXEC_ERROR':
      return `trace ${event.type} network=${event.networkId}${event.runId ? ` run=${event.runId}` : ''} error=${event.error}`;
    case 'EDGE_ACTIVE':
      return `trace ${event.type} ${event.fromNodeId}:${event.fromPort} -> ${event.toNodeId}:${event.toPort}`;
    case 'STREAM_CHUNK':
      return `trace ${event.type} node=${event.nodeId} chunk=${event.chunk.length} chars`;
    case 'AGENT_STEP':
      return `trace ${event.type} node=${event.nodeId} step=${event.step} tool=${event.tool}`;
    case 'NODE_DETAIL':
      return `trace ${event.type} node=${event.nodeId}`;
    case 'HUMAN_INPUT_REQUIRED':
      return `trace ${event.type} node=${event.nodeId}`;
    case 'NODE_PENDING':
    case 'NODE_RUNNING':
      return `trace ${event.type} node=${formatNodeLabel(event)}`;
    case 'NODE_DONE':
      return `trace ${event.type} node=${formatNodeLabel(event)} ${event.durationMs}ms`;
    case 'NODE_ERROR':
      return `trace ${event.type} node=${formatNodeLabel(event)} network=${event.networkId ?? 'unknown'} duration=${event.durationMs != null ? `${Math.round(event.durationMs)}ms` : 'unknown'} error=${event.error}`;
    case 'STEP_PAUSE':
      return `trace ${event.type} node=${event.nodeId}`;
    case 'NODE_PROGRESS':
      return `trace ${event.type} node=${event.nodeId} ${Math.round(event.progress * 100)}% ${event.message ?? ''}`.trim();
    case 'NODE_STATUS':
      return `trace ${event.type} node=${event.nodeId} ${event.status}`;
  }
}

function traceEventStatus(event: TraceEvent): 'error' | 'info' {
  return event.type === 'NODE_ERROR' || event.type === 'EXEC_ERROR' ? 'error' : 'info';
}

function summarizeMessage(msg: object): string {
  try {
    return JSON.stringify(msg);
  } catch {
    return '[unserializable message]';
  }
}

/**
 * Opens a Socket.IO connection to the trace stream and calls `onEvent` for
 * every `TraceEvent` received. Returns a stable `send` function for emitting
 * messages back to the server.
 *
 * NOTE: The Python FastAPI server (python/server/main.py) uses python-socketio.
 * This hook replaces the earlier native WebSocket implementation.
 */
export function useTraceSocket(onEvent: (e: TraceEvent) => void): { send: (msg: object) => void } {
  const cbRef = useRef<(e: TraceEvent) => void>(onEvent);
  cbRef.current = onEvent;

  // Stable ref to the live Socket so the send callback doesn't change identity.
  const socketRef = useRef<Socket | null>(null);

  const send = useCallback((msg: object) => {
    const socket = socketRef.current;
    if (socket && socket.connected) {
      // Emit as a generic 'message' event; server can handle it if needed.
      logSocket('pending', `emit message ${summarizeMessage(msg)}`);
      socket.emit('message', msg);
    } else {
      logSocket('error', 'emit message failed: Socket.IO not connected');
      console.warn('[trace] send: Socket.IO not connected');
    }
  }, []);

  useEffect(() => {
    // React StrictMode in development double-invokes effects (mount → cleanup →
    // remount). Using autoConnect:false + a cancelled flag prevents the first
    // (immediately-destroyed) socket from emitting the "closed before
    // connection established" warning.
    let cancelled = false;

    const socket: Socket = io(SOCKET_URL, {
      autoConnect: false,
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 10_000,
      transports: ['websocket', 'polling'],
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      logSocket('success', `connected ${SOCKET_URL} id=${socket.id}`);
      console.debug('[trace] Socket.IO connected, id:', socket.id);
    });

    socket.on('trace', (event: TraceEvent) => {
      logSocket(traceEventStatus(event), summarizeTraceEvent(event));
      cbRef.current(event);
    });

    socket.on('disconnect', (reason: string) => {
      logSocket('info', `disconnected ${reason}`);
      console.debug('[trace] Socket.IO disconnected:', reason);
    });

    socket.on('connect_error', (err: Error) => {
      logSocket('error', `connection error: ${err.message}`);
      console.warn('[trace] Socket.IO connection error:', err.message);
    });

    // Only connect if the effect wasn't immediately cleaned up (StrictMode)
    if (!cancelled) {
      socket.connect();
    }

    return () => {
      cancelled = true;
      socket.disconnect();
      socketRef.current = null;
    };
  }, []);

  return { send };
}
