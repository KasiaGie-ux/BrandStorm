/**
 * useSession — manages session lifecycle (start, stop, reset, navigation callbacks).
 *
 * Owns: sessionId, phase, brandKit, brandCanvas, imagePreview, firstAgentText,
 *       firstTurnDone, inputLocked, annaPlaying, showGoToSummary, voiceoverReady.
 * Exposes: handleGenerate, handleReset, handleStop, handleBack,
 *          handleLaunchComplete, handleSendMessage, handleVoiceoverEnd, handleGoToSummary.
 */

import { useState, useCallback, useRef } from 'react';

export default function useSession({
  ws,
  wsRef,
  audioPlayback,
  addMessage,
  setScreen,
  SCREENS,
}) {
  const [sessionId, setSessionId] = useState(null);
  const [phase, setPhase] = useState('INIT');
  const [brandKit, setBrandKit] = useState(null);
  const [brandCanvas, setBrandCanvas] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [firstAgentText, setFirstAgentText] = useState(null);
  const [firstTurnDone, setFirstTurnDone] = useState(false);
  const [inputLocked, setInputLocked] = useState(false);
  const [annaPlaying, setAnnaPlaying] = useState(false);
  const [showGoToSummary, setShowGoToSummary] = useState(false);
  const [voiceoverReady, setVoiceoverReady] = useState(false);

  const imageFileRef = useRef(null);
  const contextTextRef = useRef('');
  const generationTimeoutRef = useRef(null);
  const pendingResumeRef = useRef(null);
  const awaitingFirstConnect = useRef(false);
  const generationDoneRef = useRef(false);
  const voiceoverPlayedRef = useRef(false);
  const hasVoiceoverRef = useRef(false);
  const pendingResultsRef = useRef(false);
  const pendingResultsStartedRef = useRef(false);
  const micWasActiveRef = useRef(false);

  const _resetSessionState = useCallback(() => {
    setPhase('INIT');
    setBrandKit(null);
    setBrandCanvas(null);
    setFirstAgentText(null);
    setFirstTurnDone(false);
    setInputLocked(false);
    setAnnaPlaying(false);
    setShowGoToSummary(false);
    setVoiceoverReady(false);
    setImagePreview(null);
    pendingResumeRef.current = null;
    awaitingFirstConnect.current = false;
    generationDoneRef.current = false;
    voiceoverPlayedRef.current = false;
    hasVoiceoverRef.current = false;
    pendingResultsRef.current = false;
    pendingResultsStartedRef.current = false;
    micWasActiveRef.current = false;
    window._voiceoverHandoffDone = false;
    window._voiceoverGreetingDone = false;
    window._voiceoverSkipped = false;
    window._annaPendingPlay = false;
  }, []);

  const handleGenerate = useCallback((imageFile, contextText) => {
    const sid = `session-${Date.now().toString(36)}`;
    setSessionId(sid);
    _resetSessionState();
    awaitingFirstConnect.current = true;
    imageFileRef.current = imageFile;
    contextTextRef.current = contextText || '';

    audioPlayback.ensureContext();

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
  }, [ws, audioPlayback, addMessage, setScreen, SCREENS, _resetSessionState]);

  const handleLaunchComplete = useCallback(() => {
    setScreen(SCREENS.STUDIO);
    audioPlayback.ensureContext();
    if (!sessionId) return;

    const sysMsg = { type: 'text_input', text: 'SYSTEM: User has entered the Studio.' };

    if (wsRef.current?.isConnected) {
      wsRef.current.sendMessage(sysMsg);
    } else {
      pendingResumeRef.current = sysMsg.text;
      if (wsRef.current) wsRef.current.connect(sessionId);
    }
  }, [sessionId, audioPlayback, setScreen, SCREENS, wsRef]);

  const handleSendMessage = useCallback((msg) => {
    audioPlayback.flush();
    window.dispatchEvent(new CustomEvent('voiceover-stop'));

    if (msg.type === 'text_input') {
      addMessage({ type: 'user', text: msg.text });
    }
    if (!ws.isConnected && sessionId) {
      pendingResumeRef.current = msg.type === 'text_input' ? msg.text : 'Continue';
      addMessage({ type: 'agent_thinking', text: 'Reconnecting...' });
      ws.connect(sessionId);
      return;
    }
    ws.sendMessage(msg);
  }, [ws, sessionId, audioPlayback, addMessage]);

  const handleReset = useCallback(() => {
    clearTimeout(generationTimeoutRef.current);
    ws.disconnect();
    setSessionId(null);
    setScreen(SCREENS.HERO);
    imageFileRef.current = null;
    _resetSessionState();
  }, [ws, setScreen, SCREENS, _resetSessionState]);

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
  }, [ws, setScreen, SCREENS]);

  const handleVoiceoverEnd = useCallback(() => {
    voiceoverPlayedRef.current = true;
    if (wsRef.current?.sendMessage) {
      wsRef.current.sendMessage({ type: 'voiceover_playback_done' });
    }
    if (generationDoneRef.current) {
      setTimeout(() => setScreen(SCREENS.RESULTS), 1000);
    }
  }, [wsRef, setScreen, SCREENS]);

  const handleGoToSummary = useCallback(() => {
    window._voiceoverSkipped = true;
    window.dispatchEvent(new CustomEvent('voiceover-stop'));
    setAnnaPlaying(false);
    voiceoverPlayedRef.current = true;
    if (wsRef.current?.sendMessage) {
      wsRef.current.sendMessage({ type: 'go_to_summary' });
    }
  }, [wsRef]);

  return {
    // state
    sessionId,
    phase, setPhase,
    brandKit, setBrandKit,
    brandCanvas, setBrandCanvas,
    imagePreview,
    firstAgentText, setFirstAgentText,
    firstTurnDone, setFirstTurnDone,
    inputLocked, setInputLocked,
    annaPlaying, setAnnaPlaying,
    showGoToSummary, setShowGoToSummary,
    voiceoverReady, setVoiceoverReady,
    // refs (needed by useWsEvents)
    imageFileRef,
    contextTextRef,
    pendingResumeRef,
    awaitingFirstConnect,
    generationDoneRef,
    voiceoverPlayedRef,
    hasVoiceoverRef,
    pendingResultsRef,
    pendingResultsStartedRef,
    micWasActiveRef,
    // handlers
    handleGenerate,
    handleLaunchComplete,
    handleSendMessage,
    handleReset,
    handleStop,
    handleBack,
    handleVoiceoverEnd,
    handleGoToSummary,
  };
}
