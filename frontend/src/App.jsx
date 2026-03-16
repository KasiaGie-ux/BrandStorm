import { useState, useCallback, useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import HeroStage from './components/HeroStage';
import UploadStage from './components/UploadStage';
import LaunchSequence from './components/LaunchSequence';
import StudioScreen from './components/StudioScreen';
import ResultsScreen from './components/ResultsScreen';
import useWebSocket from './hooks/useWebSocket';
import useAudioPlayback from './hooks/useAudioPlayback';
import useEventQueue from './hooks/useEventQueue';
import useSession from './hooks/useSession';
import useWsEvents from './hooks/useWsEvents';
import { raw, easeCurve } from './styles/tokens';

const SCREENS = { HERO: 'hero', UPLOAD: 'upload', LAUNCH: 'launch', STUDIO: 'studio', RESULTS: 'results' };
const transition = { duration: 0.4, ease: easeCurve };

export default function App() {
  const [screen, setScreen] = useState(SCREENS.HERO);
  const [messages, setMessages] = useState([]);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const screenRef = useRef(SCREENS.HERO);
  const messagesRef = useRef([]);
  const msgIdCounter = useRef(0);

  // Refs for first-turn logic and audio/turn gating
  const firstSpeechTurnDoneRef = useRef(false);
  const launchTextRef = useRef('');
  const launchIntroRef = useRef(null);
  const turnActiveRef = useRef(false);
  const wasPlayingRef = useRef(false);
  const audioDoneTimerRef = useRef(null);
  const wsRef = useRef(null);
  const processEventRef = useRef(null);

  useEffect(() => { screenRef.current = screen; }, [screen]);

  const audioPlayback = useAudioPlayback();

  const eventQueue = useEventQueue(
    (ev) => { if (processEventRef.current) processEventRef.current(ev); },
    () => { if (wsRef.current) wsRef.current.sendMessage({ type: 'audio_playback_done' }); },
    audioPlayback.getIsPlaying,
    () => turnActiveRef.current,
  );

  // Flush event queue when audio finishes (debounced 400ms)
  useEffect(() => {
    if (audioPlayback.isPlaying) {
      wasPlayingRef.current = true;
      if (audioDoneTimerRef.current) {
        clearTimeout(audioDoneTimerRef.current);
        audioDoneTimerRef.current = null;
      }
    } else if (wasPlayingRef.current) {
      audioDoneTimerRef.current = setTimeout(() => {
        wasPlayingRef.current = false;
        audioDoneTimerRef.current = null;
        eventQueue.onAudioDone();
      }, 400);
    }
    return () => { if (audioDoneTimerRef.current) clearTimeout(audioDoneTimerRef.current); };
  }, [audioPlayback.isPlaying, eventQueue]);

  const addMessage = useCallback((msg) => {
    setMessages(prev => {
      const next = [...prev, { ...msg, _id: ++msgIdCounter.current }];
      messagesRef.current = next;
      return next;
    });
  }, []);

  // Strip known opener+intro prefix from agent text before displaying
  const stripKnownIntro = useCallback((text) => {
    const li = launchIntroRef.current;
    if (!text?.trim() || !li) return text;
    let s = text.trim();
    const { opener, intro } = li;
    for (const sep of [' ', '\n']) {
      const combined = [opener, intro].filter(Boolean).join(sep);
      if (combined && s.startsWith(combined)) return s.slice(combined.length).trim();
    }
    if (opener && s.startsWith(opener)) s = s.slice(opener.length).trim();
    if (intro && s.startsWith(intro)) s = s.slice(intro.length).trim();
    return s;
  }, []);

  // Normalize spaces when Gemini chunks arrive without spaces around punctuation
  const cleanSpacing = useCallback((text) => {
    if (!text) return text;
    return text
      .replace(/([.!?])([A-Z"'])/g, '$1 $2')
      .replace(/  +/g, ' ');
  }, []);

  const ws = useWebSocket({ onMessage: (ev) => { if (processEventRef.current) processEventRef.current(ev); }, onStatusChange: setWsStatus });
  wsRef.current = ws;

  const session = useSession({
    ws, wsRef, audioPlayback, addMessage, setScreen, SCREENS,
  });

  const handleWsMessage = useWsEvents({
    // session state setters
    setPhase: session.setPhase,
    setBrandKit: session.setBrandKit,
    setBrandCanvas: session.setBrandCanvas,
    setFirstAgentText: session.setFirstAgentText,
    setFirstTurnDone: session.setFirstTurnDone,
    setInputLocked: session.setInputLocked,
    setShowGoToSummary: session.setShowGoToSummary,
    setVoiceoverReady: session.setVoiceoverReady,
    // session refs
    imageFileRef: session.imageFileRef,
    contextTextRef: session.contextTextRef,
    pendingResumeRef: session.pendingResumeRef,
    awaitingFirstConnect: session.awaitingFirstConnect,
    generationDoneRef: session.generationDoneRef,
    hasVoiceoverRef: session.hasVoiceoverRef,
    pendingResultsRef: session.pendingResultsRef,
    micWasActiveRef: session.micWasActiveRef,
    // app-level
    addMessage,
    setMessages,
    setScreen,
    SCREENS,
    wsRef,
    audioPlayback,
    eventQueue,
    stripKnownIntro,
    cleanSpacing,
    launchTextRef,
    launchIntroRef,
    firstSpeechTurnDoneRef,
    turnActiveRef,
    msgIdCounter,
    messagesRef,
  });

  processEventRef.current = handleWsMessage;

  // Transition to results after agent audio finishes (when pending)
  const pendingResultsStartedRef = session.pendingResultsStartedRef;
  useEffect(() => {
    if (!session.pendingResultsRef.current) return;
    if (audioPlayback.isPlaying) {
      pendingResultsStartedRef.current = true;
    } else if (pendingResultsStartedRef.current) {
      session.pendingResultsRef.current = false;
      pendingResultsStartedRef.current = false;
      setTimeout(() => setScreen(SCREENS.RESULTS), 1200);
    }
  }, [audioPlayback.isPlaying]);

  // Anna (voiceover) mic lock/unlock
  useEffect(() => {
    const onStart = () => {
      session.setAnnaPlaying(true);
      session.setShowGoToSummary(true);
      window.dispatchEvent(new CustomEvent('query-mic-state', {
        detail: { callback: (isRecording) => { session.micWasActiveRef.current = isRecording; } }
      }));
      window.dispatchEvent(new CustomEvent('stop-mic'));
    };
    const onEnd = () => {
      session.setAnnaPlaying(false);
      if (session.micWasActiveRef.current) {
        session.micWasActiveRef.current = false;
        window.dispatchEvent(new CustomEvent('resume-mic'));
      }
    };
    window.addEventListener('anna-started', onStart);
    window.addEventListener('anna-ended', onEnd);
    return () => {
      window.removeEventListener('anna-started', onStart);
      window.removeEventListener('anna-ended', onEnd);
    };
  }, []);

  // Global drag-and-drop state for UploadStage
  const [dragOnPage, setDragOnPage] = useState(false);
  const dragCounterRef = useRef(0);
  useEffect(() => {
    const onDragEnter = (e) => { e.preventDefault(); dragCounterRef.current++; if (dragCounterRef.current === 1) setDragOnPage(true); };
    const onDragLeave = (e) => { e.preventDefault(); dragCounterRef.current--; if (dragCounterRef.current <= 0) { dragCounterRef.current = 0; setDragOnPage(false); } };
    const onDragOver = (e) => e.preventDefault();
    const onDrop = (e) => { e.preventDefault(); dragCounterRef.current = 0; setDragOnPage(false); };
    window.addEventListener('dragenter', onDragEnter);
    window.addEventListener('dragleave', onDragLeave);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('drop', onDrop, true);
    return () => {
      window.removeEventListener('dragenter', onDragEnter);
      window.removeEventListener('dragleave', onDragLeave);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('drop', onDrop, true);
    };
  }, []);

  // Show error in chat on permanent connection failure
  useEffect(() => {
    if (wsStatus === 'failed' && (screen === SCREENS.STUDIO || screen === SCREENS.LAUNCH)) {
      addMessage({ type: 'session_error', text: 'Your session has ended — the connection was lost.' });
    }
  }, [wsStatus, screen, addMessage]);

  return (
    <div style={{ fontFamily: "'Syne', sans-serif", minHeight: '100vh', background: raw.cream }}>
      {/* Reconnecting toast */}
      <AnimatePresence>
        {wsStatus === 'reconnecting' && (
          <motion.div
            initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
            style={{
              position: 'fixed', top: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 50,
              padding: '8px 18px', fontSize: 12, fontWeight: 700,
              fontFamily: "'Syne', sans-serif", textTransform: 'uppercase', letterSpacing: '0.1em',
              background: raw.cream, border: `2px solid ${raw.ink}`, color: raw.ink,
            }}
          >
            Reconnecting...
          </motion.div>
        )}
      </AnimatePresence>

      {/* LaunchSequence overlay */}
      <AnimatePresence>
        {screen === SCREENS.LAUNCH && (
          <LaunchSequence
            imagePreview={session.imagePreview}
            firstAgentText={session.firstAgentText}
            onComplete={session.handleLaunchComplete}
            firstTurnDone={session.firstTurnDone}
            isPlaying={audioPlayback.isPlaying}
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {screen === SCREENS.HERO && (
          <motion.div key="hero" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={transition}>
            <HeroStage onStart={() => setScreen(SCREENS.UPLOAD)} />
          </motion.div>
        )}
        {screen === SCREENS.UPLOAD && (
          <motion.div key="upload" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={transition}>
            <UploadStage onBack={() => setScreen(SCREENS.HERO)} onGenerate={session.handleGenerate} dragOnPage={dragOnPage} />
          </motion.div>
        )}
        {screen === SCREENS.STUDIO && (
          <motion.div key="studio" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={transition} style={{ height: '100vh' }}>
            <StudioScreen
              messages={messages}
              phase={session.phase}
              sendMessage={session.handleSendMessage}
              onBack={session.handleBack}
              onStop={session.handleStop}
              onReset={session.handleReset}
              imagePreview={session.imagePreview}
              onVoiceoverEnd={session.handleVoiceoverEnd}
              audioPlayback={audioPlayback}
              brandCanvas={session.brandCanvas}
              inputLocked={session.inputLocked}
              annaPlaying={session.annaPlaying}
              showGoToSummary={session.showGoToSummary}
              voiceoverReady={session.voiceoverReady}
              onGoToSummary={session.handleGoToSummary}
            />
          </motion.div>
        )}
        {screen === SCREENS.RESULTS && (
          <motion.div key="results" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={transition}>
            <ResultsScreen brandKit={session.brandKit} sessionId={session.sessionId} onReset={session.handleReset} />
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }`}</style>
    </div>
  );
}
