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
  const [brandCanvas, setBrandCanvas] = useState(null);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [imagePreview, setImagePreview] = useState(null);
  const [firstAgentText, setFirstAgentText] = useState(null);
  const [firstTurnDone, setFirstTurnDone] = useState(false);
  const launchTextRef = useRef('');
  const launchIntroRef = useRef(null); // { opener, intro } — used by stripKnownIntro
  const imageFileRef = useRef(null);
  const contextTextRef = useRef('');
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
  // Track whether the current agent turn is still active (audio or text still arriving).
  // Used by useEventQueue to gate visual event rendering until the turn ends.
  const turnActiveRef = useRef(false);

  // Keep screenRef in sync for use inside callbacks (avoids stale closures)
  useEffect(() => { screenRef.current = screen; }, [screen]);

  // processEventRef: stable ref to handleWsMessage for the event queue.
  // Set after handleWsMessage is defined (below).
  const processEventRef = useRef(null);
  const eventQueue = useEventQueue(
    (ev) => { if (processEventRef.current) processEventRef.current(ev); },
    () => { if (wsRef.current) wsRef.current.sendMessage({ type: 'audio_playback_done' }); },
    audioPlayback.getIsPlaying,          // synchronous ref-based check — no render lag
    () => turnActiveRef.current,         // synchronous turn-active check
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
      setTimeout(() => setScreen(SCREENS.RESULTS), 3000);
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

  // Strip known opener+intro prefix from any text before displaying in chat.
  // Uses the exact strings stored in launchIntroRef (from opening_sequence event).
  // Handles: "Opener. Intro sentence 1. Intro sentence 2." → ""
  // Handles: "Opener. Intro. Analysis starts here..." → "Analysis starts here..."
  const stripKnownIntro = useCallback((text) => {
    const li = launchIntroRef.current;
    if (!text?.trim() || !li) return text;
    let s = text.trim();
    const { opener, intro } = li;
    // Try stripping opener + intro together (space or newline separator)
    for (const sep of [' ', '\n']) {
      const combined = [opener, intro].filter(Boolean).join(sep);
      if (combined && s.startsWith(combined)) return s.slice(combined.length).trim();
    }
    // Try stripping opener alone, then intro
    if (opener && s.startsWith(opener)) s = s.slice(opener.length).trim();
    if (intro && s.startsWith(intro)) s = s.slice(intro.length).trim();
    return s;
  }, []);

  // Normalizes spaces when Gemini chunks missing them around punctuation/quotes
  const cleanSpacing = useCallback((text) => {
    if (!text) return text;
    return text
      // product.My -> product. My
      // innovation."Verdant -> innovation. "Verdant
      .replace(/([.!?])([A-Z"'])/g, '$1 $2')
      .replace(/  +/g, ' ');
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

      case 'agent_text': {
        const isFirstTurn = !messagesRef.current.some(m => m.type === 'agent_turn_complete');

        // If empty text, just close any dangling partial without adding new message
        if (!event.text || !event.text.trim()) {
          if (!event.partial) {
            setMessages(prev => {
              const lastIdx = prev.findLastIndex(m => m.type === 'agent_text' && m._partial);
              if (lastIdx !== -1) {
                const updated = [...prev];
                updated[lastIdx] = { ...updated[lastIdx], _partial: false };
                return updated;
              }
              return prev;
            });
          }
          break;
        }

        if (isFirstTurn) {
          // ANALYZING turn = opener + intro only. Feed to LaunchSequence, never to chat.
          const prev_text = launchTextRef.current || '';
          const needs_space = prev_text.length > 0 && event.text.length > 0 && (
            (/[.!?]$/.test(prev_text) && /^[A-Za-z]/.test(event.text)) ||
            (/[a-z]$/.test(prev_text) && /^[A-Z]/.test(event.text))
          );
          launchTextRef.current = prev_text + (needs_space ? ' ' : '') + event.text;
          const acc = launchTextRef.current;
          if (acc.trim()) setFirstAgentText(acc);
          break; // first turn never goes to chat
        }

        // --- Normal turns (> first turn) ---
        turnActiveRef.current = true;
        setMessages(prev => {
          let updatedText = event.text;
          // Find the last active partial text bubble
          const lastIdx = prev.findLastIndex(m => m.type === 'agent_text' && m._partial);
          
          if (lastIdx !== -1) {
             const last = prev[lastIdx];
             const prev_text = last.text;
             const needs_space = prev_text.length > 0 && event.text.length > 0 && (
                (/[.!?]$/.test(prev_text) && /^[A-Za-z"']/.test(event.text)) ||
                (/[a-z]$/.test(prev_text) && /^[A-Z]/.test(event.text))
             );
             updatedText = prev_text + (needs_space ? ' ' : '') + event.text;
             
             const finalOutputText = cleanSpacing(stripKnownIntro(updatedText));
             const updated = [...prev];
             // event.partial handles closing if false, otherwise remains partial
             updated[lastIdx] = { ...last, text: finalOutputText, _partial: event.partial };
             return updated;
          } else {
             const finalOutputText = cleanSpacing(stripKnownIntro(event.text));
             return [...prev, { type: 'agent_text', text: finalOutputText, _partial: event.partial, _id: ++msgIdCounter.current }];
          }
        });
        break;
      }

      case 'canvas_update':
        // Canvas state applied on agent_turn_complete to sync with event queue flush.
        // Applying here mid-turn would hide stale messages before replacements render.
        break;

      case 'agent_turn_complete':
        setMessages(prev => {
          const lastIdx = prev.findLastIndex(m => m.type === 'agent_text' && m._partial);
          if (lastIdx !== -1) {
            const updated = [...prev];
            updated[lastIdx] = { ...updated[lastIdx], _partial: false };
            return updated;
          }
          return prev;
        });
        if (event.canvas) setBrandCanvas(event.canvas);
        if (event.phase) setPhase(event.phase);
        if (!messagesRef.current.some(m => m.type === 'agent_turn_complete')) {
          setFirstTurnDone(true);
          // Store first-turn text for stripKnownIntro (prevents opener leaking into chat)
          if (launchTextRef.current) {
            launchIntroRef.current = { opener: launchTextRef.current, intro: '' };
          }
        }
        addMessage({ type: 'agent_turn_complete' });
        turnActiveRef.current = false;
        eventQueue.onTurnComplete();
        break;

      case 'tool_invoked':
        if (event.phase) setPhase(event.phase);
        addMessage({ type: 'tool_invoked', tool: event.tool, args: event.args || {}, phase: event.phase });
        break;

      case 'image_generated': {
        const newImg = {
          type: 'image_generated',
          url: event.url,
          asset_type: event.asset_type,
          label: event.asset_type?.replace('_', ' '),
          description: event.description,
          progress: event.progress,
        };
        setMessages(prev => {
          const idx = prev.findLastIndex(
            m => m.type === 'image_generated' && m.asset_type === event.asset_type
          );
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = { ...prev[idx], ...newImg };
            messagesRef.current = next;
            return next;
          }
          return [...prev, { ...newImg, _id: ++msgIdCounter.current }];
        });
        break;
      }

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
        generationDoneRef.current = true;
        // Show badge after agent text has rendered (800ms stagger)
        setTimeout(() => addMessage({ type: 'generation_complete' }), 800);
        // If no voiceover or voiceover already finished → transition after agent audio
        if (!hasVoiceoverRef.current || voiceoverPlayedRef.current) {
          if (audioPlayback.isPlaying) {
            // Agent is speaking closing sentence — wait for it to finish
            pendingResultsRef.current = true;
          } else {
            setTimeout(() => setScreen(SCREENS.RESULTS), 3000);
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
        // Replace existing tagline if present (regen), otherwise add new
        setMessages(prev => {
          const idx = prev.findLastIndex(m => m.type === 'tagline_reveal');
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = { ...prev[idx], tagline: event.tagline };
            messagesRef.current = next;
            return next;
          }
          return [...prev, { type: 'tagline_reveal', tagline: event.tagline, _id: ++msgIdCounter.current }];
        });
        break;

      case 'brand_values':
        if (event.values?.length) {
          setMessages(prev => {
            const idx = prev.findLastIndex(m => m.type === 'brand_values');
            if (idx !== -1) {
              const next = [...prev];
              next[idx] = { ...prev[idx], values: event.values };
              messagesRef.current = next;
              return next;
            }
            const next = [...prev, { type: 'brand_values', values: event.values, _id: ++msgIdCounter.current }];
            messagesRef.current = next;
            return next;
          });
        }
        break;

      case 'tone_of_voice':
        // Replace existing tone_of_voice if present (regen), otherwise add new
        setMessages(prev => {
          const idx = prev.findLastIndex(m => m.type === 'tone_of_voice');
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = { ...prev[idx], tone: event.tone_of_voice };
            messagesRef.current = next;
            return next;
          }
          return [...prev, { type: 'tone_of_voice', tone: event.tone_of_voice, _id: ++msgIdCounter.current }];
        });
        break;

      case 'brand_story':
        // Replace existing brand_story if present (regen), otherwise add new
        setMessages(prev => {
          const idx = prev.findLastIndex(m => m.type === 'brand_story');
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = { ...prev[idx], story: event.story };
            messagesRef.current = next;
            return next;
          }
          return [...prev, { type: 'brand_story', story: event.story, _id: ++msgIdCounter.current }];
        });
        break;

      case 'name_proposals': {
        // Dedup: skip only exact duplicates (same names, different send).
        // Allow new batches unconditionally — retries after rejection must show new proposals.
        setMessages(prev => {
          const lastProposal = [...prev].reverse().find(m => m.type === 'name_proposals');
          if (lastProposal) {
            const existingNames = (lastProposal.names || []).map(n => n.name).sort().join(',');
            const newNames = (event.names || []).map(n => n.name).sort().join(',');
            if (existingNames === newNames) return prev; // exact duplicate — skip
          }
          const next = [...prev, { type: 'name_proposals', names: event.names, auto_select_seconds: event.auto_select_seconds || 8, _id: ++msgIdCounter.current }];
          messagesRef.current = next;
          return next;
        });
        break;
      }

      case 'palette_reveal':
        if (event.colors?.length) {
          setMessages(prev => {
            const idx = prev.findLastIndex(m => m.type === 'palette_reveal');
            if (idx !== -1) {
              const existingColors = (prev[idx].colors || []).map(c => c.hex || c).join(',');
              const newColors = (event.colors || []).map(c => c.hex || c).join(',');
              if (existingColors === newColors) return prev; // same gen, skip
              const next = [...prev];
              next[idx] = { ...prev[idx], colors: event.colors, mood: event.mood };
              messagesRef.current = next;
              return next;
            }
            return [...prev, { type: 'palette_reveal', colors: event.colors, mood: event.mood, _id: ++msgIdCounter.current }];
          });
        }
        break;

      case 'font_suggestion':
        // Dedup: skip only if last font_suggestion has same fonts.
        setMessages(prev => {
          const lastFont = [...prev].reverse().find(m => m.type === 'font_suggestion');
          if (lastFont && lastFont.heading === event.heading && lastFont.body === event.body) return prev;
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
          turnActiveRef.current = true;
          audioPlayback.queueChunk(event.data);
        }
        break;

      case 'agent_audio_end':
        // Backend finished sending audio chunks for this turn.
        // Let the frontend queue naturally play out to completion.
        break;

      case 'agent_audio_interrupted':
        // Live API native barge-in: user spoke, server stopped generating.
        // Flush the audio queue immediately so agent stops mid-word.
        audioPlayback.flush();
        turnActiveRef.current = false;
        eventQueue.onTurnComplete();
        break;

      case 'user_voice_text':
        // Transcription of what the user said via microphone — show as user bubble.
        addMessage({ type: 'user', text: event.text });
        break;

      case 'ping':
        break;

      case 'voiceover_handoff':
        // voiceover_handoff is in VISUAL_TYPES so the event queue holds it
        // while Charon's audio plays. By the time this case runs, audio is
        // already finished — fire Anna's cue immediately.
        window._voiceoverHandoffDone = true;
        window.dispatchEvent(new CustomEvent('voiceover-handoff-ended'));
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
        // Dedup: Gemini self-interruption can trigger the tool twice
        setMessages(prev => {
          if (prev.some(m => m.type === 'voiceover_story')) return prev;
          messagesRef.current = [...prev, { type: 'voiceover_story', audio_url: event.audio_url, _id: ++msgIdCounter.current }];
          return messagesRef.current;
        });
        break;

      case 'voiceover_generated':
        // Legacy single-voice fallback
        setBrandKit(prev => prev ? { ...prev, audio_url: event.audio_url } : { audio_url: event.audio_url });
        hasVoiceoverRef.current = true;
        setMessages(prev => {
          if (prev.some(m => m.type === 'voiceover_story')) return prev;
          messagesRef.current = [...prev, { type: 'voiceover_story', audio_url: event.audio_url, _id: ++msgIdCounter.current }];
          return messagesRef.current;
        });
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
  }, [addMessage, eventQueue, audioPlayback, sessionId, stripKnownIntro]);

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
    setBrandCanvas(null);
    setFirstAgentText(null);
    setFirstTurnDone(false);
    launchTextRef.current = '';
    launchIntroRef.current = null;
    window._voiceoverHandoffDone = false;
    window._voiceoverGreetingDone = false;
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
    setScreen(SCREENS.STUDIO);
    if (!sessionId) return;
    
    const sysMsg = { 
      type: 'text_input', 
      text: 'SYSTEM: User has entered the Studio. You may now perform your visual analysis and propose names.' 
    };

    if (wsRef.current?.isConnected) {
      wsRef.current.sendMessage(sysMsg);
    } else {
      pendingResumeRef.current = sysMsg.text;
      if (wsRef.current) wsRef.current.connect(sessionId);
    }
  }, [sessionId]);

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
    setBrandCanvas(null);
    imageFileRef.current = null;
    pendingResumeRef.current = null;
    awaitingFirstConnect.current = false;
    generationDoneRef.current = false;
    voiceoverPlayedRef.current = false;
    hasVoiceoverRef.current = false;
    pendingResultsRef.current = false;
    setImagePreview(null);
    setFirstAgentText(null);
    setFirstTurnDone(false);
    launchTextRef.current = '';
    launchIntroRef.current = null;
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
            onComplete={handleLaunchComplete}
            firstTurnDone={firstTurnDone}
            isPlaying={audioPlayback.isPlaying}
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
              brandCanvas={brandCanvas}
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
