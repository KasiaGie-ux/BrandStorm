import { useRef, useCallback, useState } from 'react';

/**
 * useAudioPlayback — plays agent audio chunks (PCM 16-bit 16kHz mono)
 * sequentially via Web Audio API. Exposes analyser for VoiceIndicator.
 *
 * Usage:
 *   const { queueChunk, flush, muted, setMuted, isPlaying, analyser } = useAudioPlayback();
 *   // on agent_audio event:  queueChunk(base64Data)
 *   // on agent_audio_end:    flush()
 *   // barge-in:              flush()  (stops playback immediately)
 */
export default function useAudioPlayback() {
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const queueRef = useRef([]);
  const playingRef = useRef(false);
  const mutedRef = useRef(false);
  const [muted, _setMuted] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  // Track current source so we can stop it on flush/barge-in
  const currentSourceRef = useRef(null);

  /** Lazily create AudioContext + AnalyserNode (must happen after user gesture). */
  const ensureContext = useCallback(() => {
    if (ctxRef.current) {
      // Resume if suspended (browser autoplay policy)
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
    } catch (e) {
      console.error('AudioContext creation failed:', e);
      return null;
    }
  }, []);

  /** Decode base64 PCM 16-bit data into an AudioBuffer. */
  const decodeChunk = useCallback((base64Data) => {
    const ctx = ctxRef.current;
    if (!ctx) return null;

    const binary = atob(base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    // PCM 16-bit signed LE, mono — convert to float32
    const sampleCount = Math.floor(bytes.length / 2);
    if (sampleCount === 0) return null;

    const view = new DataView(bytes.buffer);
    // Live API audio is 24kHz PCM (the default for Gemini Live native audio)
    const sampleRate = 24000;
    const buffer = ctx.createBuffer(1, sampleCount, sampleRate);
    const channelData = buffer.getChannelData(0);

    for (let i = 0; i < sampleCount; i++) {
      const int16 = view.getInt16(i * 2, true); // little-endian
      channelData[i] = int16 / 32768;
    }

    return buffer;
  }, []);

  /** Play the next chunk in the queue. */
  const playNext = useCallback(() => {
    if (queueRef.current.length === 0) {
      playingRef.current = false;
      currentSourceRef.current = null;
      setIsPlaying(false);
      return;
    }

    playingRef.current = true;
    setIsPlaying(true);

    const base64 = queueRef.current.shift();

    // If muted, skip the chunk but keep draining the queue
    if (mutedRef.current) {
      playNext();
      return;
    }

    const buffer = decodeChunk(base64);
    if (!buffer) {
      playNext();
      return;
    }

    const ctx = ctxRef.current;
    const analyser = analyserRef.current;
    if (!ctx || !analyser) {
      playNext();
      return;
    }

    try {
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(analyser); // analyser is already connected to destination
      source.onended = () => {
        currentSourceRef.current = null;
        playNext();
      };
      currentSourceRef.current = source;
      source.start();
    } catch (e) {
      console.error('Audio playback error:', e);
      currentSourceRef.current = null;
      playNext();
    }
  }, [decodeChunk]);

  /** Queue an audio chunk for sequential playback. */
  const queueChunk = useCallback((base64Data) => {
    const ctx = ensureContext();
    if (!ctx) return;

    queueRef.current.push(base64Data);
    if (!playingRef.current) {
      playNext();
    }
  }, [ensureContext, playNext]);

  /** Stop playback immediately and clear the queue (barge-in / turn end). */
  const flush = useCallback(() => {
    queueRef.current.length = 0;
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop();
      } catch {
        // already stopped
      }
      currentSourceRef.current = null;
    }
    playingRef.current = false;
    setIsPlaying(false);
  }, []);

  /** Toggle mute — chunks still arrive but don't play. */
  const setMuted = useCallback((val) => {
    const v = typeof val === 'function' ? val(mutedRef.current) : val;
    mutedRef.current = v;
    _setMuted(v);
    // If muting while playing, stop current audio
    if (v && currentSourceRef.current) {
      try { currentSourceRef.current.stop(); } catch { /* noop */ }
      currentSourceRef.current = null;
    }
  }, []);

  return {
    queueChunk,
    flush,
    muted,
    setMuted,
    isPlaying,
    analyser: analyserRef,
    ensureContext,
  };
}
