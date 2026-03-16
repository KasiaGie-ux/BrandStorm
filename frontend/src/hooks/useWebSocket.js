import { useRef, useCallback, useEffect } from 'react';

const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
const MAX_RECONNECT = 3;
const RECONNECT_DELAY_MS = 2000;

/**
 * useWebSocket — manages WebSocket connection to backend.
 *
 * Returns { connect, disconnect, sendMessage, isConnected }
 * Calls onMessage(event) for every parsed JSON event from server.
 * Auto-reconnects up to 3 times on unexpected close.
 */
export default function useWebSocket({ onMessage, onStatusChange }) {
  const wsRef = useRef(null);
  const reconnectCount = useRef(0);
  const sessionIdRef = useRef(null);
  const intentionalClose = useRef(false);

  const updateStatus = useCallback((status) => {
    onStatusChange?.(status);
  }, [onStatusChange]);

  const connect = useCallback((sessionId) => {
    // Clean up existing connection
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
    }

    sessionIdRef.current = sessionId;
    intentionalClose.current = false;
    reconnectCount.current = 0;

    const token = new URLSearchParams(window.location.search).get('token') || '';
    const url = `${WS_BASE}/ws/${sessionId}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    updateStatus('connecting');

    ws.onopen = () => {
      reconnectCount.current = 0;
      updateStatus('connected');
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        onMessage?.(data);
      } catch {
        // Binary frame (audio) — ignore for now (Phase 5)
      }
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return; // replaced by a newer connect() call — ignore
      wsRef.current = null;
      if (intentionalClose.current) {
        updateStatus('disconnected');
        return;
      }

      // Auto-reconnect
      if (reconnectCount.current < MAX_RECONNECT) {
        reconnectCount.current++;
        updateStatus('reconnecting');
        setTimeout(() => {
          if (!intentionalClose.current) {
            connect(sessionIdRef.current);
          }
        }, RECONNECT_DELAY_MS * reconnectCount.current);
      } else {
        updateStatus('failed');
      }
    };

    ws.onerror = () => {
      // onclose will fire after this
    };
  }, [onMessage, updateStatus]);

  const disconnect = useCallback(() => {
    intentionalClose.current = true;
    wsRef.current?.close();
    wsRef.current = null;
    updateStatus('disconnected');
  }, [updateStatus]);

  const sendMessage = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      intentionalClose.current = true;
      wsRef.current?.close();
    };
  }, []);

  return {
    connect,
    disconnect,
    sendMessage,
    get isConnected() { return wsRef.current?.readyState === WebSocket.OPEN; },
  };
}
