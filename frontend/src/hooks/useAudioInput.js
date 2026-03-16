import { useRef, useCallback, useState } from 'react';

/**
 * useAudioInput — captures microphone audio as PCM 16-bit 16kHz mono
 * and sends chunks via a callback every ~256ms (4096 samples).
 *
 * Uses AudioWorklet (dedicated audio thread) to avoid frame drops
 * caused by React rendering on the main thread. Matches Google's
 * official Gemini Live API demo configuration.
 *
 * Usage:
 *   const { start, stop, isRecording, permissionDenied } = useAudioInput({ onChunk });
 *   // onChunk(base64PcmData) called every ~256ms while recording
 */

const TARGET_SAMPLE_RATE = 16000;

export default function useAudioInput({ onChunk }) {
  const [isRecording, setIsRecording] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const streamRef = useRef(null);
  const ctxRef = useRef(null);
  const workletNodeRef = useRef(null);
  const sourceRef = useRef(null);
  const recordingRef = useRef(false);

  /** Convert Float32Array to base64-encoded PCM 16-bit LE. */
  const float32ToPcm16Base64 = useCallback((float32) => {
    const buffer = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      // Symmetric clipping — matches Google's official demo
      view.setInt16(i * 2, Math.max(-32768, Math.min(32767, s * 0x7FFF)), true);
    }
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }, []);

  const start = useCallback(async () => {
    if (recordingRef.current) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: TARGET_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;
      setPermissionDenied(false);

      const ctx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: TARGET_SAMPLE_RATE,
      });
      ctxRef.current = ctx;

      // Load AudioWorklet processor (served from /public/)
      await ctx.audioWorklet.addModule('/audio-capture.worklet.js');

      const workletNode = new AudioWorkletNode(ctx, 'audio-capture-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (e) => {
        if (!recordingRef.current) return;
        const base64 = float32ToPcm16Base64(e.data);
        onChunk?.(base64);
      };

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      source.connect(workletNode);
      // Do NOT connect workletNode to destination — avoids mic feedback

      recordingRef.current = true;
      setIsRecording(true);
    } catch (e) {
      if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
        setPermissionDenied(true);
      } else {
        setPermissionDenied(true);
      }
    }
  }, [onChunk, float32ToPcm16Base64]);

  const stop = useCallback(() => {
    recordingRef.current = false;
    setIsRecording(false);

    if (workletNodeRef.current) {
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (ctxRef.current) {
      ctxRef.current.close().catch(() => {});
      ctxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
  }, []);

  return { start, stop, isRecording, permissionDenied };
}
