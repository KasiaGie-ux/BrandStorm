import { useRef, useCallback, useEffect } from 'react';

/**
 * useAnnaSession — manages Anna's WebSocket connection and audio playback.
 *
 * Opens /ws/{sessionId}/anna on anna_ready, streams audio chunks via Web Audio API,
 * and closes the connection when anna_done arrives on the main WebSocket.
 *
 * Usage:
 *   const anna = useAnnaSession();
 *   anna.open(sessionId, wsBaseUrl);   // called on anna_ready
 *   anna.close();                      // called on anna_done
 */
export default function useAnnaSession() {
  const wsRef = useRef(null);
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const queueRef = useRef([]);
  const playingRef = useRef(false);
  const currentSourceRef = useRef(null);
  const sessionIdRef = useRef(null);

  /** Lazily create a dedicated AudioContext for Anna at 24kHz. */
  const ensureContext = useCallback(() => {
    if (ctxRef.current) {
      if (ctxRef.current.state === 'suspended') {
        ctxRef.current.resume().catch(() => {});
      }
      return ctxRef.current;
    }
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;
      analyser.connect(ctx.destination);
      ctxRef.current = ctx;
      analyserRef.current = analyser;
      return ctx;
    } catch {
      return null;
    }
  }, []);

  /** Decode base64 PCM 16-bit 24kHz mono → AudioBuffer. */
  const decodeChunk = useCallback((base64Data) => {
    const ctx = ctxRef.current;
    if (!ctx) return null;

    const binary = atob(base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    const sampleCount = Math.floor(bytes.length / 2);
    if (sampleCount === 0) return null;

    const view = new DataView(bytes.buffer);
    const buffer = ctx.createBuffer(1, sampleCount, 24000);
    const channelData = buffer.getChannelData(0);
    for (let i = 0; i < sampleCount; i++) {
      channelData[i] = view.getInt16(i * 2, true) / 32768;
    }
    return buffer;
  }, []);

  /** Play next chunk from queue. */
  const playNext = useCallback(function play() {
    if (queueRef.current.length === 0) {
      playingRef.current = false;
      currentSourceRef.current = null;
      return;
    }

    playingRef.current = true;
    const base64 = queueRef.current.shift();
    const buffer = decodeChunk(base64);
    if (!buffer) { play(); return; }

    const ctx = ctxRef.current;
    const analyser = analyserRef.current;
    if (!ctx || !analyser) { play(); return; }

    try {
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(analyser);
      source.onended = () => {
        if (currentSourceRef.current !== source) return;
        currentSourceRef.current = null;
        play();
      };
      currentSourceRef.current = source;
      source.start();
    } catch {
      currentSourceRef.current = null;
      play();
    }
  }, [decodeChunk]);

  /** Queue a chunk for playback. */
  const queueChunk = useCallback((base64Data) => {
    const ctx = ensureContext();
    if (!ctx) return;
    queueRef.current.push(base64Data);
    if (!playingRef.current) playNext();
  }, [ensureContext, playNext]);

  /** Flush audio immediately (barge-in or session end). */
  const flush = useCallback(() => {
    queueRef.current.length = 0;
    const src = currentSourceRef.current;
    currentSourceRef.current = null;
    playingRef.current = false;
    if (src) { try { src.stop(); } catch { /* already stopped */ } }
  }, []);

  /** Open Anna's WebSocket connection. */
  const open = useCallback((sessionId) => {
    if (wsRef.current) return; // already open

    sessionIdRef.current = sessionId;
    ensureContext();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/${sessionId}/anna`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'agent_audio' && msg.data) {
          queueChunk(msg.data);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = (e) => {
      console.warn('[Anna WS] error', e);
    };

    ws.onclose = () => {
      wsRef.current = null;
    };
  }, [ensureContext, queueChunk]);

  /** Close Anna's WebSocket and flush audio. */
  const close = useCallback(() => {
    flush();
    const ws = wsRef.current;
    if (ws) {
      wsRef.current = null;
      try { ws.close(); } catch { /* noop */ }
    }
  }, [flush]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      close();
      if (ctxRef.current) {
        ctxRef.current.close().catch(() => {});
        ctxRef.current = null;
      }
    };
  }, [close]);

  return { open, close, flush, analyser: analyserRef };
}
