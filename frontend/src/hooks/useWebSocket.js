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
  const connectGenRef = useRef(0); // incremented on every connect() — stale onclose handlers bail out

  // Store onMessage in a ref so the WebSocket's onmessage handler always
  // calls the latest version — avoids stale closures when handleWsMessage
  // is recreated after state changes (e.g. sessionId update).
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const updateStatus = useCallback((status) => {
    onStatusChange?.(status);
  }, [onStatusChange]);

  const connect = useCallback((sessionId) => {
    // Bump generation counter — any pending onclose from previous connections will bail out
    const gen = ++connectGenRef.current;

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
      if (connectGenRef.current !== gen) return;
      reconnectCount.current = 0;
      updateStatus('connected');
    };

    ws.onmessage = (evt) => {
      if (connectGenRef.current !== gen) return;
      try {
        const data = JSON.parse(evt.data);
        onMessageRef.current?.(data);
      } catch {
        // Binary frame (audio) — ignore
      }
    };

    ws.onclose = () => {
      // Stale handler — a newer connect() call already took over
      if (connectGenRef.current !== gen) return;
      wsRef.current = null;
      if (intentionalClose.current) {
        updateStatus('disconnected');
        return;
      }

      // Auto-reconnect same session
      if (reconnectCount.current < MAX_RECONNECT) {
        reconnectCount.current++;
        updateStatus('reconnecting');
        setTimeout(() => {
          if (connectGenRef.current !== gen) return; // superseded while waiting
          if (!intentionalClose.current) connect(sessionIdRef.current);
        }, RECONNECT_DELAY_MS * reconnectCount.current);
      } else {
        updateStatus('failed');
      }
    };

    ws.onerror = () => {
      // onclose will fire after this
    };
  }, [updateStatus]);

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
