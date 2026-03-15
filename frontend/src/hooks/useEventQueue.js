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
  'font_suggestion',
  'voiceover_handoff', 'voiceover_greeting',
  'tone_of_voice',
  // tool_invoked intentionally excluded — spinner must appear immediately
  // image_generated intentionally excluded — image must appear immediately when ready,
  // not wait for agent audio to finish (breaks regeneration when session drops mid-queue)
]);

const STAGGER_MS = 600;

/**
 * @param {Function} processEvent — callback to process a single event
 * @param {Function} onFlushComplete — called after all queued events are flushed
 * @param {Function} isAudioPlayingFn — synchronous getter: () => boolean
 *        Must read a ref (not React state) to avoid render-cycle lag.
 * @param {Function} isTurnActiveFn — synchronous getter: () => boolean
 *        Must read a ref (not React state) to avoid render-cycle lag.
 */
export default function useEventQueue(processEvent, onFlushComplete, isAudioPlayingFn, isTurnActiveFn) {
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

  /**
   * Called when agent audio finishes playing.
   * Flushes only if the turn is already complete — otherwise onTurnComplete will flush.
   */
  const onAudioDone = useCallback(() => {
    const isTurnActive = isTurnActiveFn ? isTurnActiveFn() : false;
    if (!isTurnActive) {
      flush();
    }
    // If turn still active, onTurnComplete will flush when agent_turn_complete arrives
  }, [flush, isTurnActiveFn]);

  /**
   * Called when agent_turn_complete arrives.
   * Flushes only if audio is already done — otherwise onAudioDone will flush.
   */
  const onTurnComplete = useCallback(() => {
    const isPlaying = isAudioPlayingFn ? isAudioPlayingFn() : false;
    if (!isPlaying) {
      flush();
    }
    // If audio still playing, onAudioDone will flush when it finishes
  }, [flush, isAudioPlayingFn]);

  /**
   * Try to enqueue a visual event. Returns true if queued (caller should skip),
   * false if not (caller should process immediately).
   *
   * Queues if audio is playing OR if the turn is still active (prevents cards
   * from appearing while the agent is still speaking).
   */
  const enqueue = useCallback((event) => {
    const isPlaying = isAudioPlayingFn ? isAudioPlayingFn() : false;
    const isTurnActive = isTurnActiveFn ? isTurnActiveFn() : false;
    if (VISUAL_TYPES.has(event.type) && (isPlaying || isTurnActive)) {
      queue.current.push(event);
      return true;
    }
    return false;
  }, [isAudioPlayingFn, isTurnActiveFn]);

  // Cleanup on unmount — cancel any pending stagger timers
  useEffect(() => {
    return () => {
      flushTimers.current.forEach(t => clearTimeout(t));
      flushTimers.current = [];
    };
  }, []);

  // Expose queue length for checking if empty
  const getQueueLength = useCallback(() => queue.current.length, []);

  return { enqueue, onAudioDone, onTurnComplete, getQueueLength };
}
