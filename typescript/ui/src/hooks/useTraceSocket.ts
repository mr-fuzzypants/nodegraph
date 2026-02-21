import { useEffect, useRef, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import type { TraceEvent } from '../types/traceTypes';

const SOCKET_URL = 'http://localhost:3001';

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
      socket.emit('message', msg);
    } else {
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
      console.debug('[trace] Socket.IO connected, id:', socket.id);
    });

    socket.on('trace', (event: TraceEvent) => {
      cbRef.current(event);
    });

    socket.on('disconnect', (reason: string) => {
      console.debug('[trace] Socket.IO disconnected:', reason);
    });

    socket.on('connect_error', (err: Error) => {
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
