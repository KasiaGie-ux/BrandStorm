import { useRef, useCallback, useState } from 'react';

/**
 * useAudioInput — captures microphone audio as PCM 16-bit 16kHz mono
 * and sends chunks via a callback every ~250ms.
 *
 * Uses ScriptProcessorNode (deprecated but universally supported)
 * to get raw PCM. AudioWorklet would be cleaner but requires a
 * separate worker file — overkill for a hackathon.
 *
 * Usage:
 *   const { start, stop, isRecording, permissionDenied } = useAudioInput({ onChunk });
 *   // onChunk(base64PcmData) called every ~250ms while recording
 */

// Silence detection disabled — mic stays on until user toggles it off.
// Live API handles barge-in natively; no need to auto-stop.
const SILENCE_THRESHOLD = 0.005; // kept for potential future VAD use
const TARGET_SAMPLE_RATE = 16000;

export default function useAudioInput({ onChunk, onSilenceTimeout }) {
  const [isRecording, setIsRecording] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const streamRef = useRef(null);
  const ctxRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const recordingRef = useRef(false);

  /** Downsample from source rate to 16kHz. */
  const downsample = useCallback((float32Array, fromRate) => {
    if (fromRate === TARGET_SAMPLE_RATE) return float32Array;
    const ratio = fromRate / TARGET_SAMPLE_RATE;
    const newLength = Math.floor(float32Array.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      result[i] = float32Array[Math.floor(i * ratio)];
    }
    return result;
  }, []);

  /** Convert Float32Array to base64-encoded PCM 16-bit LE. */
  const float32ToPcm16Base64 = useCallback((float32) => {
    const buffer = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }, []);

  // No-op: silence timer disabled — mic stays always on
  const resetSilenceTimer = useCallback(() => {}, []);

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

      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      ctxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessorNode with 4096 buffer (~93ms at 44.1kHz)
      // Send every ~20ms per Live API best practices (20-40ms chunks recommended)
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      let accumulatedChunks = [];
      let accumulatedLength = 0;
      const TARGET_CHUNK_SAMPLES = Math.floor(TARGET_SAMPLE_RATE * 0.02); // ~20ms

      processor.onaudioprocess = (e) => {
        if (!recordingRef.current) return;

        const input = e.inputBuffer.getChannelData(0);
        const downsampled = downsample(new Float32Array(input), ctx.sampleRate);
        accumulatedChunks.push(downsampled);
        accumulatedLength += downsampled.length;

        // Check for silence
        let rms = 0;
        for (let i = 0; i < downsampled.length; i++) {
          rms += downsampled[i] * downsampled[i];
        }
        rms = Math.sqrt(rms / downsampled.length);

        if (rms > SILENCE_THRESHOLD) {
          resetSilenceTimer();
        }

        // Send every ~250ms worth of samples
        if (accumulatedLength >= TARGET_CHUNK_SAMPLES) {
          const samples = new Float32Array(accumulatedLength);
          let offset = 0;
          for (const chunk of accumulatedChunks) {
            samples.set(chunk, offset);
            offset += chunk.length;
          }
          accumulatedChunks = [];
          accumulatedLength = 0;
          const base64 = float32ToPcm16Base64(samples);
          onChunk?.(base64);
        }
      };

      source.connect(processor);
      processor.connect(ctx.destination); // required for onaudioprocess to fire

      recordingRef.current = true;
      setIsRecording(true);
      resetSilenceTimer();
    } catch (e) {
      // Microphone access failed — handle gracefully
      if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
        setPermissionDenied(true);
      }
    }
  }, [onChunk, downsample, float32ToPcm16Base64, resetSilenceTimer]);

  const stop = useCallback(() => {
    recordingRef.current = false;
    setIsRecording(false);

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
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
