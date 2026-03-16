/**
 * useWsEvents — handles all incoming WebSocket events from the backend.
 *
 * Owns: the full handleWsMessage switch dispatch.
 * Returns: handleWsMessage (stable useCallback).
 */

import { useCallback, useRef } from 'react';

export default function useWsEvents({
  // from useSession
  setPhase,
  setBrandKit,
  setBrandCanvas,
  setFirstAgentText,
  setFirstTurnDone,
  setInputLocked,
  setShowGoToSummary,
  setVoiceoverReady,
  imageFileRef,
  contextTextRef,
  pendingResumeRef,
  awaitingFirstConnect,
  generationDoneRef,
  hasVoiceoverRef,
  pendingResultsRef,
  micWasActiveRef,
  // from App
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
}) {
  const handleWsMessage = useCallback((event) => {
    const { type } = event;

    // Unlock input immediately on image done — don't wait for queue flush
    if (type === 'image_generated') {
      setInputLocked(false);
      if (micWasActiveRef.current) {
        micWasActiveRef.current = false;
        window.dispatchEvent(new CustomEvent('resume-mic'));
      }
    }

    // Delegate visual events to queue while audio plays
    if (eventQueue.enqueue(event)) return;

    switch (type) {
      case 'session_ready': {
        if (pendingResumeRef.current) {
          const resumeText = pendingResumeRef.current;
          pendingResumeRef.current = null;
          const isStudioEntry = resumeText.toLowerCase().includes('user has entered the studio');
          if (isStudioEntry) {
            wsRef.current?.sendMessage({ type: 'text_input', text: resumeText });
          } else if (imageFileRef.current) {
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
            wsRef.current?.sendMessage({ type: 'text_input', text: resumeText });
          }
          setPhase('GENERATING');
          break;
        }
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
        addMessage({ type: 'agent_text', text: 'Connection was lost. Your session could not be resumed — please start over if generation stalled.' });
        break;
      }

      case 'agent_text': {
        const isFirstTurn = !firstSpeechTurnDoneRef.current;
        if (event.text && event.text.includes('[CANVAS STATE]')) break;

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
          const prev_text = launchTextRef.current || '';
          const needs_space = prev_text.length > 0 && event.text.length > 0 && (
            (/[.!?]$/.test(prev_text) && /^[A-Za-z]/.test(event.text)) ||
            (/[a-z]$/.test(prev_text) && /^[A-Z]/.test(event.text))
          );
          launchTextRef.current = prev_text + (needs_space ? ' ' : '') + event.text;
          if (launchTextRef.current.trim()) setFirstAgentText(launchTextRef.current);
          break;
        }

        setPhase(p => p === 'INIT' || p === 'ANALYZING' ? 'PROPOSING' : p);
        turnActiveRef.current = true;
        setMessages(prev => {
          const lastIdx = prev.findLastIndex(m => m.type === 'agent_text' && m._partial);
          if (lastIdx !== -1) {
            const last = prev[lastIdx];
            const prev_text = last.text;
            const needs_space = prev_text.length > 0 && event.text.length > 0 && (
              (/[.!?]$/.test(prev_text) && /^[A-Za-z"']/.test(event.text)) ||
              (/[a-z]$/.test(prev_text) && /^[A-Z]/.test(event.text))
            );
            const updatedText = prev_text + (needs_space ? ' ' : '') + event.text;
            const updated = [...prev];
            updated[lastIdx] = { ...last, text: cleanSpacing(stripKnownIntro(updatedText)), _partial: event.partial };
            return updated;
          }
          return [...prev, {
            type: 'agent_text',
            text: cleanSpacing(stripKnownIntro(event.text)),
            _partial: event.partial,
            _id: ++msgIdCounter.current,
          }];
        });
        break;
      }

      case 'canvas_update':
        if (event.canvas?.instagram?.status === 'ready') {
          setShowGoToSummary(true);
          setVoiceoverReady(true);
        }
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
        if (!firstSpeechTurnDoneRef.current && launchTextRef.current) {
          firstSpeechTurnDoneRef.current = true;
          setFirstTurnDone(true);
          launchIntroRef.current = { opener: launchTextRef.current, intro: '' };
        }
        setInputLocked(false);
        addMessage({ type: 'agent_turn_complete' });
        turnActiveRef.current = false;
        eventQueue.onTurnComplete();
        window.dispatchEvent(new CustomEvent('agent-presenting-done'));
        if (micWasActiveRef.current) {
          micWasActiveRef.current = false;
          window.dispatchEvent(new CustomEvent('resume-mic'));
        }
        break;

      case 'tool_invoked':
        if (event.phase) setPhase(event.phase);
        else if (event.tool === 'analyze_product') setPhase('ANALYZING');
        addMessage({ type: 'tool_invoked', tool: event.tool, args: event.args || {}, phase: event.phase });
        {
          const MIC_OFF_TOOLS = new Set(['generate_image', 'generate_voiceover', 'set_brand_identity', 'set_palette', 'set_fonts']);
          if (MIC_OFF_TOOLS.has(event.tool)) {
            micWasActiveRef.current = false;
            window.dispatchEvent(new CustomEvent('query-mic-state', {
              detail: { callback: (isRecording) => { micWasActiveRef.current = isRecording; } }
            }));
            window.dispatchEvent(new CustomEvent('stop-mic'));
          }
          if (MIC_OFF_TOOLS.has(event.tool)) setInputLocked(true);
        }
        break;

      case 'image_generated': {
        const bustedUrl = event.url ? `${event.url}?v=${Date.now()}` : event.url;
        const newImg = {
          type: 'image_generated',
          url: bustedUrl,
          asset_type: event.asset_type,
          label: event.label || event.asset_type?.replace(/_/g, ' '),
          description: event.description,
          progress: event.progress,
        };
        setMessages(prev => {
          const next = [...prev, { ...newImg, _id: ++msgIdCounter.current }];
          messagesRef.current = next;
          return next;
        });
        break;
      }

      case 'generation_complete': {
        const { type: _, ...kitData } = event;
        setBrandKit(prev => ({
          ...prev,
          brand_name: event.brand_name,
          asset_urls: event.asset_urls || {},
          zip_url: event.zip_url,
          ...kitData,
        }));
        generationDoneRef.current = true;
        setTimeout(() => addMessage({ type: 'generation_complete' }), 800);
        if (audioPlayback.isPlaying) {
          pendingResultsRef.current = true;
        } else {
          setTimeout(() => setScreen(SCREENS.RESULTS), 2500);
        }
        break;
      }

      case 'brand_name_reveal':
        addMessage({ type: 'brand_name_reveal', name: event.name, rationale: event.rationale });
        break;

      case 'brand_name_reveal_rationale':
        addMessage({ type: 'brand_name_reveal_rationale', rationale: event.rationale });
        break;

      case 'tagline_reveal':
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
        setMessages(prev => {
          const lastProposal = [...prev].reverse().find(m => m.type === 'name_proposals');
          if (lastProposal) {
            const existingNames = (lastProposal.names || []).map(n => n.name).sort().join(',');
            const newNames = (event.names || []).map(n => n.name).sort().join(',');
            if (existingNames === newNames) return prev;
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
              if (existingColors === newColors) return prev;
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
        break;

      case 'agent_audio_interrupted':
        audioPlayback.flush();
        turnActiveRef.current = false;
        eventQueue.onTurnComplete();
        break;

      case 'user_voice_text':
        addMessage({ type: 'user', text: event.text });
        break;

      case 'ping':
        wsRef.current?.sendMessage({ type: 'pong' });
        break;

      case 'voiceover_story':
      case 'voiceover_generated':
        setBrandKit(prev => prev ? { ...prev, audio_url: event.audio_url } : { audio_url: event.audio_url });
        hasVoiceoverRef.current = true;
        setVoiceoverReady(true);
        setInputLocked(false);
        if (micWasActiveRef.current) {
          micWasActiveRef.current = false;
          window.dispatchEvent(new CustomEvent('resume-mic'));
        }
        setMessages(prev => {
          if (prev.some(m => m.type === 'voiceover_story')) return prev;
          const next = [...prev, { type: 'voiceover_story', audio_url: event.audio_url, _id: ++msgIdCounter.current }];
          messagesRef.current = next;
          return next;
        });
        break;

      case 'session_timeout':
        addMessage({ type: 'session_error', text: 'Your session has ended — it timed out.' });
        break;

      case 'error':
        addMessage({ type: 'session_error', text: event.message || 'Something went wrong. Your session has ended.' });
        break;

      default:
        break;
    }
  }, [
    addMessage, setMessages, setScreen, SCREENS,
    setPhase, setBrandKit, setBrandCanvas,
    setFirstAgentText, setFirstTurnDone,
    setInputLocked, setShowGoToSummary, setVoiceoverReady,
    audioPlayback, eventQueue, wsRef,
    stripKnownIntro, cleanSpacing,
    imageFileRef, contextTextRef, pendingResumeRef,
    awaitingFirstConnect, generationDoneRef, hasVoiceoverRef,
    pendingResultsRef, micWasActiveRef,
    launchTextRef, launchIntroRef,
    firstSpeechTurnDoneRef, turnActiveRef,
    msgIdCounter, messagesRef,
  ]);

  return handleWsMessage;
}
