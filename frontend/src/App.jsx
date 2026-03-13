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
import { raw, easeCurve } from './styles/tokens';

const SCREENS = { HERO: 'hero', UPLOAD: 'upload', LAUNCH: 'launch', STUDIO: 'studio', RESULTS: 'results' };

const transition = { duration: 0.4, ease: easeCurve };

export default function App() {
  const [screen, setScreen] = useState(SCREENS.HERO);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [phase, setPhase] = useState('INIT');
  const [brandKit, setBrandKit] = useState(null);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [imagePreview, setImagePreview] = useState(null);
  const [firstAgentText, setFirstAgentText] = useState(null);
  const [openingData, setOpeningData] = useState(null); // { words: [...], intro: "..." }
  const launchTextRef = useRef('');
  const imageFileRef = useRef(null);
  const contextTextRef = useRef('');
  const firstTextCaptured = useRef(false);
  const openingReceived = useRef(false);
  const generationTimeoutRef = useRef(null);
  const messagesRef = useRef([]);
  const pendingResumeRef = useRef(null);
  const awaitingFirstConnect = useRef(false);
  const generationDoneRef = useRef(false);
  const screenRef = useRef(SCREENS.HERO);
  const voiceoverPlayedRef = useRef(false);
  const hasVoiceoverRef = useRef(false);
  const pendingResultsRef = useRef(false); // waiting for agent audio to finish before results

  // Audio playback for agent voice
  const audioPlayback = useAudioPlayback();
  const wasPlayingRef = useRef(false);
  const audioDoneTimerRef = useRef(null);
  const wsRef = useRef(null);

  // Keep screenRef in sync for use inside callbacks (avoids stale closures)
  useEffect(() => { screenRef.current = screen; }, [screen]);

  // processEventRef: stable ref to handleWsMessage for the event queue.
  // Set after handleWsMessage is defined (below).
  const processEventRef = useRef(null);
  const eventQueue = useEventQueue(
    (ev) => { if (processEventRef.current) processEventRef.current(ev); },
    () => { if (wsRef.current) wsRef.current.sendMessage({ type: 'audio_playback_done' }); },
    audioPlayback.getIsPlaying,   // synchronous ref-based check — no render lag
  );

  // Detect audio done transition → flush the event queue.
  // Debounced 400ms to avoid premature flush between audio chunks.
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
    return () => {
      if (audioDoneTimerRef.current) clearTimeout(audioDoneTimerRef.current);
    };
  }, [audioPlayback.isPlaying, eventQueue]);

  // When pendingResults is set, transition to results after agent audio finishes
  useEffect(() => {
    if (!pendingResultsRef.current) return;
    if (!audioPlayback.isPlaying) {
      pendingResultsRef.current = false;
      setTimeout(() => setScreen(SCREENS.RESULTS), 1500);
    }
  }, [audioPlayback.isPlaying]);

  // Drag state lifted for UploadStage
  const [dragOnPage, setDragOnPage] = useState(false);
  const dragCounterRef = useRef(0);

  useEffect(() => {
    const onDragEnter = (e) => {
      e.preventDefault();
      dragCounterRef.current++;
      if (dragCounterRef.current === 1) setDragOnPage(true);
    };
    const onDragLeave = (e) => {
      e.preventDefault();
      dragCounterRef.current--;
      if (dragCounterRef.current <= 0) {
        dragCounterRef.current = 0;
        setDragOnPage(false);
      }
    };
    const onDragOver = (e) => e.preventDefault();
    const onDrop = (e) => {
      e.preventDefault();
      dragCounterRef.current = 0;
      setDragOnPage(false);
    };
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

  const msgIdCounter = useRef(0);
  const addMessage = useCallback((msg) => {
    setMessages(prev => {
      const next = [...prev, { ...msg, _id: ++msgIdCounter.current }];
      messagesRef.current = next;
      return next;
    });
  }, []);

  const handleWsMessage = useCallback((event) => {
    const { type } = event;

    // Delegate visual events to the event queue while audio is playing
    if (eventQueue.enqueue(event)) {
      return;
    }

    switch (type) {
      case 'session_ready':
        // Resume after stop: send the pending message + product image for context
        if (pendingResumeRef.current) {
          const resumeText = pendingResumeRef.current;
          pendingResumeRef.current = null;
          // Re-send product image so the new Live API session has visual context
          if (imageFileRef.current) {
            const reader = new FileReader();
            reader.onload = (e) => {
              const base64 = e.target.result.split(',')[1];
              wsRef.current?.sendMessage({
                type: 'image_upload',
                data: base64,
                mime_type: imageFileRef.current.type || 'image/jpeg',
                context: `RESUMING SESSION. User says: ${resumeText}. Continue where you left off.`,
              });
            };
            reader.readAsDataURL(imageFileRef.current);
          } else {
            // No image, just send the text
            wsRef.current?.sendMessage({ type: 'text_input', text: resumeText });
          }
          setPhase('GENERATING');
          break;
        }
        // First connect — upload image
        if (awaitingFirstConnect.current) {
          awaitingFirstConnect.current = false;
          if (imageFileRef.current) {
            const reader = new FileReader();
            reader.onload = (e) => {
              const base64 = e.target.result.split(',')[1];
              wsRef.current?.sendMessage({
                type: 'image_upload',
                data: base64,
                mime_type: imageFileRef.current.type || 'image/jpeg',
                context: contextTextRef.current,
              });
            };
            reader.onerror = () => {
              addMessage({ type: 'agent_text', text: 'Failed to read image file. Please go back and try again.' });
            };
            reader.readAsDataURL(imageFileRef.current);
          }
          break;
        }
        // Reconnect (connection lost mid-session)
        addMessage({ type: 'agent_text', text: 'Connection was lost. Your session could not be resumed — please start over if generation stalled.' });
        break;

      case 'opening_sequence':
        // Reliable text from backend text-model call (parallel to Live API audio).
        // This is the definitive source for LaunchSequence display.
        if (!openingReceived.current && event.words?.length >= 2) {
          openingReceived.current = true;
          firstTextCaptured.current = true; // stop accumulating transcription
          setOpeningData({ words: event.words, intro: event.intro || '' });
          // Also set firstAgentText so LaunchSequence triggers
          const wordsStr = event.words.map(w => w + '.').join(' ');
          setFirstAgentText(wordsStr + '\n' + (event.intro || ''));
        }
        break;

      case 'agent_text':
        // Accumulate agent text during launch phase for LaunchSequence parsing.
        // Opening sequence text goes ONLY to LaunchSequence, NOT to chat messages.
        if (!firstTextCaptured.current && event.text) {
          // Non-partial = final consolidated text from backend (turn_complete flush).
          if (event.partial === false) {
            launchTextRef.current = event.text;
            setFirstAgentText(event.text);
            firstTextCaptured.current = true;
          } else {
            // Partial chunks — accumulate incrementally
            launchTextRef.current += event.text;
            const acc = launchTextRef.current;
            const periodCount = (acc.match(/\./g) || []).length;
            if (periodCount >= 2) {
              setFirstAgentText(acc);
            }
            if (periodCount >= 4) {
              firstTextCaptured.current = true;
            }
          }
          // ALWAYS break — opener/intro text is for LaunchSequence only, never chat
          break;
        }

        // After firstTextCaptured, agent_text flows to chat messages normally.
        // (The opener is already blocked above; analysis text should appear in chat.)

        // Empty text = turn boundary or closing a partial.
        if (!event.text || !event.text.trim()) {
          if (!firstTextCaptured.current) {
            // Opening turn ended. Close the launch accumulation gate —
            // the opener + intro (if any) are captured in launchTextRef.
            // Push final accumulated text to LaunchSequence.
            const acc = launchTextRef.current;
            if (acc) {
              setFirstAgentText(acc);
            }
            firstTextCaptured.current = true;
            break;
          }
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last && last.type === 'agent_text' && last._partial) {
              const updated = [...prev];
              updated[updated.length - 1] = { ...last, _partial: false };
              return updated;
            }
            return prev;
          });
          break;
        }
        if (event.partial) {
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last && last.type === 'agent_text' && last._partial) {
              const updated = [...prev];
              const prev_text = last.text;
              const needs_space = prev_text.length > 0 && (
                (/[.!?]$/.test(prev_text) && /^[A-Za-z]/.test(event.text)) ||
                (/[a-z]$/.test(prev_text) && /^[A-Z]/.test(event.text))
              );
              updated[updated.length - 1] = { ...last, text: prev_text + (needs_space ? ' ' : '') + event.text };
              return updated;
            }
            return [...prev, { type: 'agent_text', text: event.text, _partial: true, _id: ++msgIdCounter.current }];
          });
        } else {
          setMessages(prev => {
            const last = prev[prev.length - 1];
            // If empty text, just close any dangling partial without adding new message
            if (!event.text || !event.text.trim()) {
              if (last && last.type === 'agent_text' && last._partial) {
                const updated = [...prev];
                updated[updated.length - 1] = { ...last, _partial: false };
                return updated;
              }
              return prev;
            }

            let outputText = event.text;

            // Strip text that was already shown in LaunchSequence.
            // Compare normalized words — if outputText starts with the launch
            // text, remove the overlapping prefix so only analysis remains.
            if (launchTextRef.current && outputText) {
              const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g, '');
              const launchNorm = norm(launchTextRef.current);
              const outNorm = norm(outputText);
              if (launchNorm.length > 20 && outNorm.startsWith(launchNorm.substring(0, Math.floor(launchNorm.length * 0.7)))) {
                // Find a sentence boundary in the original text near the end of the launch portion
                const launchWordCount = launchTextRef.current.split(/\s+/).length;
                const outWords = outputText.split(/\s+/);
                // Skip past the launch words, then find the next sentence start
                let cutIdx = Math.min(launchWordCount, outWords.length);
                // Scan forward for a capital letter (sentence start)
                while (cutIdx < outWords.length && !/^[A-Z]/.test(outWords[cutIdx])) cutIdx++;
                const rest = outWords.slice(cutIdx).join(' ').trim();
                if (rest) {
                  outputText = rest;
                } else {
                  // Nothing left after stripping — skip this message entirely
                  return prev;
                }
              }
            }

            // Replace the last partial (still open)
            if (last && last.type === 'agent_text' && last._partial) {
              const updated = [...prev];
              updated[updated.length - 1] = { ...last, text: outputText, _partial: false };
              return updated;
            }

            // Replace the last agent_text in the same turn-block.
            // Only a USER message creates a real boundary — structured events
            // (palette_reveal, font_suggestion etc.) can appear between the
            // partial text and the non-partial narration within the same turn.
            for (let i = prev.length - 1; i >= 0; i--) {
              const m = prev[i];
              if (m.type === 'agent_text') {
                const updated = [...prev];
                updated[i] = { ...m, text: outputText, _partial: false };
                return updated;
              }
              if (m.type === 'user') break; // only user input = real turn boundary
            }

            return [...prev, { type: 'agent_text', text: outputText, _id: ++msgIdCounter.current }];
          });
        }
        break;

      case 'agent_turn_complete':
        if (event.phase) setPhase(event.phase);
        addMessage({ type: 'agent_turn_complete' });
        // Backup: if no audio was generated for this turn, signal readiness.
        // Uses getIsPlaying() (sync ref) — NOT isPlaying (async state).
        // 1200ms gives the audio pipeline time to start before we conclude
        // "no audio this turn" and fire the fallback.
        setTimeout(() => {
          if (!audioPlayback.getIsPlaying() && eventQueue.getQueueLength() === 0) {
            if (wsRef.current) wsRef.current.sendMessage({ type: 'audio_playback_done' });
          }
        }, 1200);
        break;

      case 'tool_invoked':
        if (event.phase) setPhase(event.phase);
        addMessage({ type: 'tool_invoked', tool: event.tool, args: event.args || {}, phase: event.phase });
        break;

      case 'image_generated':
        addMessage({
          type: 'image_generated',
          url: event.url,
          asset_type: event.asset_type,
          label: event.asset_type?.replace('_', ' '),
          description: event.description,
          progress: event.progress,
        });
        break;

      case 'generation_complete': {
        clearTimeout(generationTimeoutRef.current);
        const { type: _, ...kitData } = event;
        setBrandKit(prev => ({
          ...prev,
          brand_name: event.brand_name,
          asset_urls: event.asset_urls || {},
          zip_url: event.zip_url,
          ...kitData,
        }));
        addMessage({ type: 'generation_complete' });
        generationDoneRef.current = true;
        // If no voiceover or voiceover already finished → transition after agent audio
        if (!hasVoiceoverRef.current || voiceoverPlayedRef.current) {
          if (audioPlayback.isPlaying) {
            // Agent is speaking closing sentence — wait for it to finish
            pendingResultsRef.current = true;
          } else {
            setTimeout(() => setScreen(SCREENS.RESULTS), 1500);
          }
        }
        // Otherwise wait for onVoiceoverEnd callback
        break;
      }

      case 'brand_name_reveal':
        addMessage({ type: 'brand_name_reveal', name: event.name, rationale: event.rationale });
        break;

      case 'brand_name_reveal_rationale':
        addMessage({ type: 'brand_name_reveal_rationale', rationale: event.rationale });
        break;

      case 'tagline_reveal':
        addMessage({ type: 'tagline_reveal', tagline: event.tagline });
        break;

      case 'brand_values':
        addMessage({ type: 'brand_values', values: event.values });
        break;

      case 'tone_of_voice':
        addMessage({ type: 'tone_of_voice', tone: event.tone_of_voice });
        break;

      case 'brand_story':
        addMessage({ type: 'brand_story', story: event.story });
        break;

      case 'name_proposals':
        // Delay so the analysis text has time to appear first.
        // User can start reading the analysis before names pop in.
        setTimeout(() => {
          addMessage({
            type: 'name_proposals', names: event.names,
            auto_select_seconds: event.auto_select_seconds || 10,
          });
        }, 2500);
        break;

      case 'palette_reveal':
        if (event.colors?.length) {
          // Dedup: skip if palette already rendered (tool call + text parser can both emit)
          setMessages(prev => {
            if (prev.some(m => m.type === 'palette_reveal')) return prev;
            return [...prev, { type: 'palette_reveal', colors: event.colors, mood: event.mood, _id: ++msgIdCounter.current }];
          });
        }
        break;

      case 'font_suggestion':
        // Dedup: skip if font_suggestion already rendered
        setMessages(prev => {
          if (prev.some(m => m.type === 'font_suggestion')) return prev;
          return [...prev, {
            type: 'font_suggestion',
            heading: event.heading, body: event.body,
            rationale: event.rationale, _id: ++msgIdCounter.current,
          }];
        });
        break;

      case 'agent_narration':
        addMessage({ type: 'agent_narration', text: event.text });
        break;

      case 'agent_thinking':
        addMessage({ type: 'agent_thinking', text: event.text });
        break;

      case 'agent_audio':
        if (event.data) {
          audioPlayback.queueChunk(event.data);
        }
        break;

      case 'agent_audio_end':
        audioPlayback.flush();
        break;

      case 'ping':
        break;

      case 'voiceover_handoff':
        // Stop agent's Live API audio so it doesn't overlap with Anna
        audioPlayback.flush();
        // Charon's handoff line — small muted text + auto-play audio
        addMessage({ type: 'voiceover_handoff', audio_url: event.audio_url, text: event.text });
        break;

      case 'voiceover_greeting':
        // Anna's greeting — auto-plays before story narration
        addMessage({ type: 'voiceover_greeting', audio_url: event.audio_url, text: event.text });
        break;

      case 'voiceover_story':
        // Stop any remaining agent audio before Anna speaks
        audioPlayback.flush();
        // Anna's brand story narration — the deliverable
        setBrandKit(prev => prev ? { ...prev, audio_url: event.audio_url } : { audio_url: event.audio_url });
        hasVoiceoverRef.current = true;
        addMessage({ type: 'voiceover_story', audio_url: event.audio_url });
        break;

      case 'voiceover_generated':
        // Legacy single-voice fallback
        setBrandKit(prev => prev ? { ...prev, audio_url: event.audio_url } : { audio_url: event.audio_url });
        hasVoiceoverRef.current = true;
        addMessage({ type: 'voiceover_story', audio_url: event.audio_url });
        break;

      case 'session_timeout':
        addMessage({ type: 'agent_text', text: `Session timed out: ${event.message}` });
        break;

      case 'error':
        addMessage({ type: 'agent_text', text: `Error: ${event.message}` });
        break;

      default:
        break;
    }
  }, [addMessage, eventQueue, audioPlayback, sessionId]);

  // Keep processEventRef in sync so the event queue can call handleWsMessage
  processEventRef.current = handleWsMessage;

  const ws = useWebSocket({
    onMessage: handleWsMessage,
    onStatusChange: setWsStatus,
  });
  // Keep wsRef in sync
  wsRef.current = ws;

  const handleGenerate = useCallback((imageFile, contextText) => {
    const sid = `session-${Date.now().toString(36)}`;
    setSessionId(sid);
    setMessages([]);
    messagesRef.current = [];
    setPhase('INIT');
    setBrandKit(null);
    setFirstAgentText(null);
    setOpeningData(null);
    openingReceived.current = false;
    firstTextCaptured.current = false;
    launchTextRef.current = '';
    pendingResumeRef.current = null;
    awaitingFirstConnect.current = true;
    generationDoneRef.current = false;
    voiceoverPlayedRef.current = false;
    hasVoiceoverRef.current = false;
    pendingResultsRef.current = false;
    imageFileRef.current = imageFile;
    contextTextRef.current = contextText || '';

    // Create preview for LaunchSequence + StudioScreen
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target.result);
    reader.onerror = () => addMessage({ type: 'agent_text', text: 'Failed to load image preview.' });
    reader.readAsDataURL(imageFile);

    ws.connect(sid);
    setScreen(SCREENS.LAUNCH);
    addMessage({ type: 'agent_thinking', text: 'Connecting to Brand Architect...' });

    clearTimeout(generationTimeoutRef.current);
    generationTimeoutRef.current = setTimeout(() => {
      addMessage({ type: 'agent_text', text: 'Session timed out after 15 minutes. Please try again.' });
      setScreen(SCREENS.RESULTS);
    }, 15 * 60 * 1000);
  }, [ws, addMessage]);

  const handleLaunchComplete = useCallback(() => {
    // Ensure we stop accumulating launch text
    firstTextCaptured.current = true;

    setScreen(SCREENS.STUDIO);
  }, []);

  const handleSendMessage = useCallback((msg) => {
    // Barge-in: stop agent audio when user sends anything
    audioPlayback.flush();
    // Also stop any voiceover <audio> elements (Anna's narration)
    window.dispatchEvent(new CustomEvent('voiceover-stop'));

    if (msg.type === 'text_input') {
      addMessage({ type: 'user', text: msg.text });
    }
    // If WS is disconnected (e.g. after stop), reconnect and queue the message
    if (!ws.isConnected && sessionId) {
      pendingResumeRef.current = msg.type === 'text_input' ? msg.text : 'Continue';
      addMessage({ type: 'agent_thinking', text: 'Reconnecting...' });
      ws.connect(sessionId);
      return;
    }
    ws.sendMessage(msg);
  }, [ws, sessionId, addMessage]);

  const handleReset = useCallback(() => {
    clearTimeout(generationTimeoutRef.current);
    ws.disconnect();
    setScreen(SCREENS.HERO);
    setSessionId(null);
    setMessages([]);
    setPhase('INIT');
    setBrandKit(null);
    imageFileRef.current = null;
    pendingResumeRef.current = null;
    awaitingFirstConnect.current = false;
    generationDoneRef.current = false;
    voiceoverPlayedRef.current = false;
    hasVoiceoverRef.current = false;
    pendingResultsRef.current = false;
    setImagePreview(null);
    setFirstAgentText(null);
    setOpeningData(null);
    openingReceived.current = false;
    firstTextCaptured.current = false;
    launchTextRef.current = '';
  }, [ws]);

  const handleStop = useCallback(() => {
    clearTimeout(generationTimeoutRef.current);
    ws.sendMessage({ type: 'stop_session' });
    ws.disconnect();
    setPhase('STOPPED');
    addMessage({ type: 'agent_text', text: 'Session paused. Type a message or say something to resume.' });
  }, [ws, addMessage]);

  const handleVoiceoverEnd = useCallback(() => {
    voiceoverPlayedRef.current = true;
    // Signal backend that voiceover playback is complete —
    // unblocks finalize nudge in auto-continue logic.
    if (wsRef.current && wsRef.current.sendMessage) {
      wsRef.current.sendMessage({ type: 'voiceover_playback_done' });
    }
    if (generationDoneRef.current) {
      setTimeout(() => setScreen(SCREENS.RESULTS), 1000);
    }
  }, []);

  const handleBack = useCallback(() => {
    ws.disconnect();
    setScreen(SCREENS.UPLOAD);
  }, [ws]);

  return (
    <div style={{
      fontFamily: "'Syne', sans-serif",
      minHeight: '100vh', background: raw.cream,
    }}>
      {/* Connection toast */}
      <AnimatePresence>
        {(wsStatus === 'reconnecting' || wsStatus === 'failed') && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            style={{
              position: 'fixed', top: 16, left: '50%',
              transform: 'translateX(-50%)', zIndex: 50,
              padding: '8px 18px', fontSize: 12, fontWeight: 700,
              fontFamily: "'Syne', sans-serif",
              textTransform: 'uppercase', letterSpacing: '0.1em',
              background: raw.cream,
              border: `2px solid ${wsStatus === 'failed' ? raw.red : raw.ink}`,
              color: wsStatus === 'failed' ? raw.red : raw.ink,
            }}
          >
            {wsStatus === 'reconnecting' ? 'Reconnecting...' : 'Connection failed. Please refresh.'}
          </motion.div>
        )}
      </AnimatePresence>

      {/* LaunchSequence overlay */}
      <AnimatePresence>
        {screen === SCREENS.LAUNCH && (
          <LaunchSequence
            imagePreview={imagePreview}
            firstAgentText={firstAgentText}
            openingData={openingData}
            onComplete={handleLaunchComplete}
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {screen === SCREENS.HERO && (
          <motion.div key="hero"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }} transition={transition}
          >
            <HeroStage onStart={() => setScreen(SCREENS.UPLOAD)} />
          </motion.div>
        )}
        {screen === SCREENS.UPLOAD && (
          <motion.div key="upload"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }} transition={transition}
          >
            <UploadStage
              onBack={() => setScreen(SCREENS.HERO)}
              onGenerate={handleGenerate}
              dragOnPage={dragOnPage}
            />
          </motion.div>
        )}
        {screen === SCREENS.STUDIO && (
          <motion.div key="studio"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }} transition={transition}
            style={{ height: '100vh' }}
          >
            <StudioScreen
              messages={messages}
              phase={phase}
              sendMessage={handleSendMessage}
              onBack={handleBack}
              onStop={handleStop}
              imagePreview={imagePreview}
              onVoiceoverEnd={handleVoiceoverEnd}
              audioPlayback={audioPlayback}
            />
          </motion.div>
        )}
        {screen === SCREENS.RESULTS && (
          <motion.div key="results"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }} transition={transition}
          >
            <ResultsScreen
              brandKit={brandKit}
              sessionId={sessionId}
              onReset={handleReset}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
