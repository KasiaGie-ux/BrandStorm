import { useRef, useCallback, useEffect } from 'react';

/**
 * useEventQueue — queues visual events while agent audio is playing,
 * then flushes them with stagger when audio finishes.
 *
 * Architecture:
 *   1. `enqueue(event)` checks audio state SYNCHRONOUSLY via `isAudioPlayingFn`
 *      (reads a ref, not React state — zero render-cycle lag).
 *   2. While audio plays, visual events accumulate in the queue.
 *   3. When audio stops, the App's useEffect calls `onAudioDone()`,
 *      which flushes queued events with 600ms stagger.
 *   4. After the last event is flushed, `onFlushComplete` fires —
 *      this sends `audio_playback_done` to the backend so the next
 *      auto-continue nudge can proceed.
 *
 * This keeps the agent→visual flow sequential:
 *   agent speaks → finishes → cards appear one by one → backend nudges next step.
 */

const VISUAL_TYPES = new Set([
  'brand_name_reveal', 'tagline_reveal',
  'brand_story', 'brand_values', 'palette_reveal',
  'font_suggestion', 'tool_invoked', 'image_generated',
  'voiceover_handoff', 'voiceover_story', 'generation_complete',
  'tone_of_voice',
]);

const STAGGER_MS = 600;

/**
 * @param {Function} processEvent — callback to process a single event
 * @param {Function} onFlushComplete — called after all queued events are flushed
 * @param {Function} isAudioPlayingFn — synchronous getter: () => boolean
 *        Must read a ref (not React state) to avoid render-cycle lag.
 *        Typically `audioPlayback.getIsPlaying`.
 */
export default function useEventQueue(processEvent, onFlushComplete, isAudioPlayingFn) {
  const queue = useRef([]);
  const flushTimers = useRef([]);

  const flush = useCallback(() => {
    const events = [...queue.current];
    queue.current = [];
    // Clear any pending flush timers
    flushTimers.current.forEach(t => clearTimeout(t));
    flushTimers.current = [];

    if (events.length === 0) {
      if (onFlushComplete) onFlushComplete();
      return;
    }

    events.forEach((ev, i) => {
      const t = setTimeout(() => {
        processEvent(ev);
        if (i === events.length - 1 && onFlushComplete) {
          onFlushComplete();
        }
      }, i * STAGGER_MS);
      flushTimers.current.push(t);
    });
  }, [processEvent, onFlushComplete]);

  const onAudioDone = useCallback(() => {
    flush();
  }, [flush]);

  /**
   * Try to enqueue a visual event. Returns true if queued (caller should skip),
   * false if not (caller should process immediately).
   *
   * Uses `isAudioPlayingFn()` — a SYNCHRONOUS ref read — so there's
   * no gap between audio starting and the queue becoming active.
   */
  const enqueue = useCallback((event) => {
    const isPlaying = isAudioPlayingFn ? isAudioPlayingFn() : false;
    if (VISUAL_TYPES.has(event.type) && isPlaying) {
      queue.current.push(event);
      return true;
    }
    return false;
  }, [isAudioPlayingFn]);

  // Cleanup on unmount — cancel any pending stagger timers
  useEffect(() => {
    return () => {
      flushTimers.current.forEach(t => clearTimeout(t));
      flushTimers.current = [];
    };
  }, []);

  // Expose queue length for checking if empty
  const getQueueLength = useCallback(() => queue.current.length, []);

  return { enqueue, onAudioDone, getQueueLength };
}
