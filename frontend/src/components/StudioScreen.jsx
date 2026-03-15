import { useRef, useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import ProgressTracker from './ProgressTracker';
import MessageBubble, { ImageTile, ProductOverlay, ImageOverlay } from './MessageBubble';
import useAudioInput from '../hooks/useAudioInput';
import VoiceIndicator from './VoiceIndicator';
import { raw, fonts } from '../styles/tokens';

const DISPLAY_TYPES = [
  'agent_text', 'agent_narration', 'user',
  'brand_reveal', 'brand_name_reveal', 'brand_name_reveal_rationale',
  'tagline_reveal', 'brand_values', 'brand_story', 'tone_of_voice',
  'name_proposals',
  'image_generated', 'tool_invoked', 'generation_complete',
  'palette_reveal', 'palette_ready', 'font_suggestion',
  'voiceover_greeting', 'voiceover_story',
];

export default function StudioScreen({ messages, phase, sendMessage, onBack, onStop, onReset, imagePreview, onVoiceoverEnd, audioPlayback, brandCanvas, inputLocked }) {
  const scrollRef = useRef(null);
  const [input, setInput] = useState('');
  const [showOverlay, setShowOverlay] = useState(false);
  const [imageOverlay, setImageOverlay] = useState(null);
  // Stable ref so onaudioprocess closure always reads the latest getIsPlaying
  // without causing useAudioInput to recreate its processor on every render.
  const getIsPlayingRef = useRef(null);
  getIsPlayingRef.current = audioPlayback?.getIsPlaying ?? null;

  // Mic input — sends PCM chunks to backend as audio_chunk events.
  // While agent audio plays, only forward chunks that are loud enough to be
  // a real barge-in (RMS > threshold). This lets echoCancellation handle
  // normal speaker bleed while still allowing the user to interrupt loudly.
  const BARGE_IN_RMS = 0.04; // ~-28 dBFS — clearly a human voice, not echo
  const handleAudioChunk = useCallback((base64Data) => {
    if (!getIsPlayingRef.current?.()) {
      // Agent silent — always send
      sendMessage({ type: 'audio_chunk', data: base64Data });
      return;
    }
    // Agent speaking — only send if RMS exceeds barge-in threshold
    try {
      const binary = atob(base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const samples = new Int16Array(bytes.buffer);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += (samples[i] / 32768) ** 2;
      const rms = Math.sqrt(sum / samples.length);
      if (rms > BARGE_IN_RMS) {
        sendMessage({ type: 'audio_chunk', data: base64Data });
      }
    } catch {
      // decode error — skip chunk
    }
  }, [sendMessage]); // getIsPlayingRef read via ref — no dep needed

  const audioInput = useAudioInput({
    onChunk: handleAudioChunk,
  });

  // Respond to App-level lock/unlock events so App can query and restore mic state
  useEffect(() => {
    const onQueryMic = (e) => {
      if (e.detail?.callback) e.detail.callback(audioInput.isRecording);
    };
    const onStopMic = () => {
      if (audioInput.isRecording) audioInput.stop();
    };
    const onResumeMic = () => {
      if (!audioInput.isRecording) audioInput.start();
    };
    window.addEventListener('query-mic-state', onQueryMic);
    window.addEventListener('resume-mic', onResumeMic);
    window.addEventListener('stop-mic', onStopMic);
    return () => {
      window.removeEventListener('query-mic-state', onQueryMic);
      window.removeEventListener('resume-mic', onResumeMic);
      window.removeEventListener('stop-mic', onStopMic);
    };
  }, [audioInput]);

  // Stop mic immediately when input becomes locked
  useEffect(() => {
    if (inputLocked && audioInput.isRecording) {
      audioInput.stop();
    }
  }, [inputLocked, audioInput]);

  const handleMicToggle = useCallback(() => {
    // Ensure AudioContext is initialized (requires user gesture)
    audioPlayback?.ensureContext();
    if (audioInput.isRecording) {
      audioInput.stop();
    } else {
      // Barge-in: stop agent audio when user starts recording
      audioPlayback?.flush();
      audioInput.start();
    }
  }, [audioInput, audioPlayback]);

  // Canvas-first: read brand name and tagline from canvas, fall back to messages
  const brandName = brandCanvas?.name?.value
    || [...messages].reverse().find(m => m.type === 'brand_name_reveal')?.name
    || [...messages].reverse().find(m => m.type === 'brand_reveal')?.name || '';
  const tagline = brandCanvas?.tagline?.value
    || [...messages].reverse().find(m => m.type === 'tagline_reveal')?.tagline || '';

  // Canvas-first: derive progress from canvas element statuses
  const completedEvents = [];
  if (brandCanvas) {
    if (brandCanvas.palette?.status === 'ready') completedEvents.push('palette_reveal');
    if (brandCanvas.logo?.status === 'ready') completedEvents.push('image:logo');
    if (brandCanvas.hero?.status === 'ready') completedEvents.push('image:hero');
    if (brandCanvas.instagram?.status === 'ready') completedEvents.push('image:instagram');
  } else {
    messages.forEach(m => {
      if (m.type === 'palette_reveal' || m.type === 'palette_ready') completedEvents.push('palette_reveal');
      if (m.type === 'image_generated') completedEvents.push(`image:${m.asset_type}`);
    });
  }

  // Canvas-aware stale detection: hide messages for stale elements
  // Images are never hidden — all generated images remain visible in chat history
  const isStaleByCanvas = (msg) => {
    if (!brandCanvas) return false;
    switch (msg.type) {
      case 'image_generated':
        return false; // always show all image tiles, including older ones
      case 'palette_reveal':
      case 'palette_ready':
        return brandCanvas.palette?.status === 'stale';
      case 'font_suggestion':
        return brandCanvas.fonts?.status === 'stale';
      case 'brand_name_reveal':
      case 'brand_name_reveal_rationale':
        return brandCanvas.name?.status === 'stale';
      case 'tagline_reveal':
        return brandCanvas.tagline?.status === 'stale';
      case 'brand_story':
        return brandCanvas.story?.status === 'stale';
      case 'brand_values':
        return brandCanvas.values?.status === 'stale';
      case 'tone_of_voice':
        return brandCanvas.tone?.status === 'stale';
      default:
        return false;
    }
  };

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!showOverlay) return;
    const onKey = (e) => { if (e.key === 'Escape') setShowOverlay(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showOverlay]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text) return;
    sendMessage({ type: 'text_input', text });
    setInput('');
  }, [input, sendMessage]);

  const handleImageClick = useCallback((src, label) => {
    setImageOverlay({ src, label });
  }, []);

  const TOOL_RESULT_MAP = {
    generate_image: 'image_generated',
    generate_palette: 'palette_reveal',
    propose_names: 'name_proposals',
    reveal_brand_identity: 'brand_name_reveal',
    suggest_fonts: 'font_suggestion',
    finalize_brand_kit: 'generation_complete',
    generate_voiceover: 'voiceover_story',
  };
  // Build ranges where agent_text should be hidden
  // (narration between name_proposals and user's choice — NOT after the user picks)
  const hideRanges = [];
  let lastProposalIdx = -1;
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].type === 'name_proposals') {
      if (lastProposalIdx !== -1) hideRanges.push([lastProposalIdx, i]);
      lastProposalIdx = i;
    } else if (messages[i].type === 'user' && lastProposalIdx !== -1) {
      // User picked a name — stop hiding. Narration AFTER this must be visible.
      hideRanges.push([lastProposalIdx, i]);
      lastProposalIdx = -1;
    } else if (messages[i].type === 'brand_name_reveal' && lastProposalIdx !== -1) {
      hideRanges.push([lastProposalIdx, i]);
      lastProposalIdx = -1;
    }
  }
  // If proposals still open (no reveal yet), hide through end
  if (lastProposalIdx !== -1) hideRanges.push([lastProposalIdx, messages.length]);

  // The LAST name_proposals is the active one for countdown
  const lastProposalMsgIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].type === 'name_proposals') return i;
    }
    return -1;
  })();

  const displayMessages = messages.filter((m, i) => {
    if (!DISPLAY_TYPES.includes(m.type)) return false;
    // Hide tool_invoked spinner if a result for this tool exists later in messages
    if (m.type === 'tool_invoked' && m.tool) {
      const instantTools = ['generate_palette', 'generate_voiceover', 'propose_names',
        'reveal_brand_identity', 'suggest_fonts', 'set_brand_identity', 'set_palette', 'set_fonts'];
      if (instantTools.includes(m.tool)) return false;
      const resultType = TOOL_RESULT_MAP[m.tool];
      if (resultType) {
        const hasResult = messages.slice(i + 1).some(later => later.type === resultType);
        if (hasResult) return false;
      }
    }
    // Hide agent_text inside any name narration range
    if (m.type === 'agent_text' && hideRanges.some(([start, end]) => i > start && i < end)) {
      return false;
    }
    // Canvas-aware: hide messages for elements the canvas marks as stale
    if (isStaleByCanvas(m)) return false;
    return true;
  });
  // Countdown starts only after agent finishes narrating all 3 names.
  // Two gates: agent_turn_complete must fire AND agent audio must stop playing.
  const hasAgentTurnCompleteAfterProposals = lastProposalMsgIdx !== -1
    && messages.slice(lastProposalMsgIdx + 1).some(m => m.type === 'agent_turn_complete');
  const agentAudioPlaying = audioPlayback?.isPlaying ?? false;

  // Freeze countdown when user has reacted (sent any message after proposals appeared).
  // This covers both "I don't like those names" and voice feedback cases.
  const proposalsFrozen = lastProposalMsgIdx !== -1
    && messages.slice(lastProposalMsgIdx + 1).some(m => m.type === 'user');

  const [nameNarrationDone, setNameNarrationDone] = useState(false);
  const lastProposalIdxRef = useRef(-1);

  useEffect(() => {
    // Reset if proposals changed (new round)
    if (lastProposalMsgIdx !== lastProposalIdxRef.current) {
      lastProposalIdxRef.current = lastProposalMsgIdx;
      setNameNarrationDone(false);
    }

    // Agent finished generating AND audio finished playing → narration done
    if (hasAgentTurnCompleteAfterProposals && !agentAudioPlaying && !nameNarrationDone && lastProposalMsgIdx !== -1) {
      setNameNarrationDone(true);
    }
  }, [hasAgentTurnCompleteAfterProposals, agentAudioPlaying, lastProposalMsgIdx, nameNarrationDone]);

  const isGenerating = phase === 'GENERATING' || phase === 'REFINING';
  const isStopped = phase === 'STOPPED';

  return (
    <div style={{
      position: 'relative', zIndex: 1,
      height: '100vh', display: 'flex', flexDirection: 'column',
    }}>
      {/* Red stripe */}
      <div style={{
        position: 'fixed', top: 0, left: 0, bottom: 0,
        width: 5, background: raw.red, zIndex: 10,
      }} />

      {/* Header */}
      <div style={{
        display: 'flex', flexDirection: 'column',
        padding: '12px 24px 0',
        borderBottom: `1px solid ${raw.line}`,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 16,
          paddingBottom: 8,
        }}>
          <button type="button" aria-label="Go back" onClick={onBack} style={{
            background: 'none', border: `2px solid ${raw.line}`,
            cursor: 'pointer', fontSize: 14, color: raw.muted,
            padding: '6px 14px', fontFamily: fonts.body,
            transition: 'all 0.3s',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = raw.red; e.currentTarget.style.color = raw.red; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = raw.line; e.currentTarget.style.color = raw.muted; }}
          >‹</button>

          {imagePreview && (
            <div onClick={() => setShowOverlay(true)} style={{
              width: 40, height: 40, overflow: 'hidden',
              border: `2px solid ${raw.ink}`, cursor: 'pointer',
              flexShrink: 0,
            }}>
              <img src={imagePreview} alt="Product"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
          )}

          {brandName && (
            <span style={{
              fontFamily: fonts.display, fontSize: 16,
              textTransform: 'uppercase', color: raw.ink,
              letterSpacing: '0.04em',
            }}>{brandName}</span>
          )}

          <div style={{ flex: 1 }} />

          {/* Voice indicator — pulses when agent is speaking */}
          {audioPlayback?.isPlaying && (
            <VoiceIndicator analyserRef={audioPlayback.analyser} />
          )}

          {/* Mute/unmute agent audio */}
          {audioPlayback && (
            <button
              type="button"
              aria-label={audioPlayback.muted ? 'Unmute agent' : 'Mute agent'}
              onClick={() => audioPlayback.setMuted(v => !v)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 4, display: 'flex', alignItems: 'center',
                color: audioPlayback.muted ? raw.faint : raw.ink,
                transition: 'color 0.2s',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {audioPlayback.muted ? (
                  <>
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <line x1="23" y1="9" x2="17" y2="15" />
                    <line x1="17" y1="9" x2="23" y2="15" />
                  </>
                ) : (
                  <>
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                  </>
                )}
              </svg>
            </button>
          )}

          <span style={{
            fontFamily: fonts.mono, fontSize: 10, color: raw.faint,
            textTransform: 'uppercase', letterSpacing: '0.1em',
          }}>{phase || 'INIT'}</span>
        </div>

        <ProgressTracker phase={phase} completedEvents={completedEvents} brandCanvas={brandCanvas} />
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        flex: 1, overflow: 'auto', padding: '24px 24px 16px',
        maxWidth: 640, width: '100%', margin: '0 auto',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {displayMessages.map((msg) => {
            const key = msg._id != null ? `m-${msg._id}` : `m-${msg.type}-${msg.url || msg.name || ''}`;
            if (msg.type === 'image_generated') {
              return <ImageTile key={key} msg={msg} onImageClick={handleImageClick} onImageLoad={scrollToBottom} />;
            }
            return (
              <MessageBubble
                key={key}
                msg={msg}
                sendMessage={sendMessage}
                brandName={brandName}
                tagline={tagline}
                onVoiceoverEnd={onVoiceoverEnd}
                nameNarrationDone={nameNarrationDone}
                proposalsFrozen={proposalsFrozen}
                onStopAudio={() => audioPlayback?.flush()}
                onReset={onReset}
              />
            );
          })}
        </div>
      </div>

      {/* Input bar */}
      <div style={{
        padding: '0 24px 20px',
        background: `linear-gradient(to top, ${raw.cream} 60%, transparent)`,
      }}>
        <AnimatePresence>
          {inputLocked && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              style={{ maxWidth: 640, margin: '0 auto', paddingBottom: 6 }}
            >
              <div style={{
                fontSize: 11,
                color: raw.muted,
                fontFamily: fonts.body,
                fontStyle: 'italic',
                letterSpacing: '0.04em',
              }}>
                Generating — input locked
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {(isGenerating || isStopped) && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              style={{ maxWidth: 640, margin: '0 auto', paddingBottom: 8 }}
            >
              <div style={{
                fontSize: 12,
                color: isStopped ? raw.red : raw.faint,
                fontFamily: fonts.body,
                fontStyle: 'italic',
                fontWeight: isStopped ? 600 : 400,
              }}>
                {isStopped
                  ? 'Session paused — type a message to resume.'
                  : "Don't like something? Tell the agent to change it."}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div style={{
          display: 'flex', gap: 10, alignItems: 'center',
          maxWidth: 640, margin: '0 auto',
          border: `2px solid ${raw.line}`,
          padding: '10px 14px',
          background: 'rgba(255,255,255,0.4)',
        }}>
          {/* Mic button */}
          <button
            type="button"
            aria-label={audioInput.isRecording ? 'Stop recording' : 'Start recording'}
            onClick={handleMicToggle}
            title={inputLocked ? 'Input locked during generation' : audioInput.permissionDenied ? 'Microphone unavailable — type instead' : ''}
            disabled={audioInput.permissionDenied || inputLocked}
            style={{
              width: 34, height: 34,
              border: audioInput.isRecording ? `2px solid ${raw.red}` : `2px solid ${raw.line}`,
              cursor: (audioInput.permissionDenied || inputLocked) ? 'not-allowed' : 'pointer',
              background: audioInput.isRecording ? raw.red : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s', flexShrink: 0,
              opacity: (audioInput.permissionDenied || inputLocked) ? 0.4 : 1,
              position: 'relative',
            }}
          >
            {/* Recording pulse */}
            {audioInput.isRecording && (
              <span style={{
                position: 'absolute', top: -2, right: -2,
                width: 8, height: 8, background: raw.red,
                animation: 'micPulse 1s ease-in-out infinite',
              }} />
            )}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke={audioInput.isRecording ? raw.white : raw.muted}
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              style={{ transition: 'stroke 0.2s' }}
            >
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </button>

          {audioInput.isRecording && (
            <span style={{
              fontSize: 11, color: raw.red, fontFamily: fonts.body,
              fontWeight: 600, whiteSpace: 'nowrap',
            }}>Listening...</span>
          )}

          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !inputLocked && handleSend()}
            placeholder={inputLocked ? 'Generating... input locked' : audioInput.isRecording ? 'Or type here...' : 'Tell the agent what you think...'}
            disabled={inputLocked}
            style={{
              flex: 1, border: 'none', background: 'transparent',
              fontSize: 14, color: inputLocked ? raw.muted : raw.ink,
              fontFamily: fonts.body,
              cursor: inputLocked ? 'not-allowed' : 'text',
            }}
          />
          {onStop && phase !== 'INIT' && phase !== 'COMPLETE' && phase !== 'STOPPED' && (
            <button
              type="button"
              aria-label="Stop agent"
              onClick={onStop}
              style={{
                width: 34, height: 34, border: `2px solid ${raw.red}`,
                cursor: 'pointer', background: 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.2s', flexShrink: 0,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = raw.red; e.currentTarget.querySelector('svg').style.stroke = raw.white; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.querySelector('svg').style.stroke = raw.red; }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke={raw.red} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                style={{ transition: 'stroke 0.2s' }}
              >
                <rect x="6" y="6" width="12" height="12" />
              </svg>
            </button>
          )}
          <button
            type="button"
            aria-label="Send message"
            onClick={handleSend}
            disabled={!input.trim() || inputLocked}
            style={{
              width: 34, height: 34, border: 'none',
              cursor: (input.trim() && !inputLocked) ? 'pointer' : 'default',
              background: (input.trim() && !inputLocked) ? raw.red : raw.line,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'background 0.2s', flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke={(input.trim() && !inputLocked) ? raw.white : raw.faint}
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              style={{ transition: 'stroke 0.2s' }}
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>

      </div>

      {/* Overlays */}
      <AnimatePresence>
        {showOverlay && (
          <ProductOverlay imagePreview={imagePreview} onClose={() => setShowOverlay(false)} />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {imageOverlay && (
          <ImageOverlay
            src={imageOverlay.src}
            label={imageOverlay.label}
            onClose={() => setImageOverlay(null)}
          />
        )}
      </AnimatePresence>

      <style>{`
        @keyframes micPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(1.4); }
        }
      `}</style>
    </div>
  );
}
