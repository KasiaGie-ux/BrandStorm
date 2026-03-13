import { useState, useCallback, useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import HeroStage from './components/HeroStage';
import UploadStage from './components/UploadStage';
import LaunchSequence from './components/LaunchSequence';
import StudioScreen from './components/StudioScreen';
import ResultsScreen from './components/ResultsScreen';
import useWebSocket from './hooks/useWebSocket';
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
  const imageFileRef = useRef(null);
  const contextTextRef = useRef('');
  const firstTextCaptured = useRef(false);
  const generationTimeoutRef = useRef(null);
  const messagesRef = useRef([]);
  const pendingResumeRef = useRef(null);
  const awaitingFirstConnect = useRef(false);

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
              ws.sendMessage({
                type: 'image_upload',
                data: base64,
                mime_type: imageFileRef.current.type || 'image/jpeg',
                context: `RESUMING SESSION. User says: ${resumeText}. Continue where you left off.`,
              });
            };
            reader.readAsDataURL(imageFileRef.current);
          } else {
            // No image, just send the text
            ws.sendMessage({ type: 'text_input', text: resumeText });
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
              ws.sendMessage({
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

      case 'agent_text':
        // Capture first agent text for LaunchSequence
        if (!firstTextCaptured.current && event.text) {
          firstTextCaptured.current = true;
          setFirstAgentText(event.text);
        }
        if (event.partial) {
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last && last.type === 'agent_text' && last._partial) {
              const updated = [...prev];
              updated[updated.length - 1] = { ...last, text: last.text + event.text };
              return updated;
            }
            return [...prev, { type: 'agent_text', text: event.text, _partial: true, _id: ++msgIdCounter.current }];
          });
        } else {
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last && last.type === 'agent_text' && last._partial) {
              const updated = [...prev];
              updated[updated.length - 1] = { ...last, type: 'agent_text', text: event.text, _partial: false };
              return updated;
            }
            return [...prev, { type: 'agent_text', text: event.text, _id: ++msgIdCounter.current }];
          });
        }
        break;

      case 'agent_turn_complete':
        if (event.phase) setPhase(event.phase);
        addMessage({ type: 'agent_turn_complete' });
        break;

      case 'tool_invoked':
        if (event.phase) setPhase(event.phase);
        addMessage({ type: 'tool_invoked', tool: event.tool, args: event.args || {}, phase: event.phase });
        break;

      case 'image_generated':
        console.log('[WS] image_generated event:', event.asset_type, event.url);
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
        setBrandKit({
          brand_name: event.brand_name,
          asset_urls: event.asset_urls || {},
          zip_url: event.zip_url,
          ...kitData,
        });
        addMessage({ type: 'generation_complete' });
        setTimeout(() => setScreen(SCREENS.RESULTS), 1500);
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

      case 'brand_story':
        addMessage({ type: 'brand_story', story: event.story });
        break;

      case 'name_proposals':
        addMessage({
          type: 'name_proposals', names: event.names,
          auto_select_seconds: event.auto_select_seconds || 10,
        });
        break;

      case 'palette_reveal':
        if (event.colors?.length) {
          addMessage({ type: 'palette_reveal', colors: event.colors, mood: event.mood });
        }
        break;

      case 'font_suggestion':
        addMessage({
          type: 'font_suggestion',
          heading: event.heading, body: event.body,
          rationale: event.rationale,
        });
        break;

      case 'agent_narration':
        addMessage({ type: 'agent_narration', text: event.text });
        break;

      case 'agent_thinking':
        addMessage({ type: 'agent_thinking', text: event.text });
        break;

      case 'agent_audio':
      case 'ping':
        break;

      case 'voiceover_generated':
        // Store audio_url in brandKit state — will be picked up on generation_complete
        setBrandKit(prev => prev ? { ...prev, audio_url: event.audio_url } : { audio_url: event.audio_url });
        addMessage({ type: 'voiceover_generated', audio_url: event.audio_url });
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
  }, [addMessage]);

  const ws = useWebSocket({
    onMessage: handleWsMessage,
    onStatusChange: setWsStatus,
  });

  const handleGenerate = useCallback((imageFile, contextText) => {
    const sid = `session-${Date.now().toString(36)}`;
    setSessionId(sid);
    setMessages([]);
    messagesRef.current = [];
    setPhase('INIT');
    setBrandKit(null);
    setFirstAgentText(null);
    firstTextCaptured.current = false;
    pendingResumeRef.current = null;
    awaitingFirstConnect.current = true;
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
      addMessage({ type: 'agent_text', text: 'Session timed out after 3 minutes. Please try again.' });
      setScreen(SCREENS.RESULTS);
    }, 3 * 60 * 1000);
  }, [ws, addMessage]);

  const handleLaunchComplete = useCallback(() => {
    setScreen(SCREENS.STUDIO);
  }, []);

  const handleSendMessage = useCallback((msg) => {
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
    setImagePreview(null);
    setFirstAgentText(null);
    firstTextCaptured.current = false;
  }, [ws]);

  const handleStop = useCallback(() => {
    clearTimeout(generationTimeoutRef.current);
    ws.sendMessage({ type: 'stop_session' });
    ws.disconnect();
    setPhase('STOPPED');
    addMessage({ type: 'agent_text', text: 'Session paused. Type a message or say something to resume.' });
  }, [ws, addMessage]);

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
