import { useRef, useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import ProgressTracker from './ProgressTracker';
import MessageBubble, { ImageTile, ProductOverlay, ImageOverlay } from './MessageBubble';
import { raw, fonts } from '../styles/tokens';

const DISPLAY_TYPES = [
  'agent_text', 'agent_narration', 'user',
  'brand_reveal', 'brand_name_reveal', 'brand_name_reveal_rationale',
  'tagline_reveal', 'brand_values', 'brand_story',
  'name_proposals',
  'image_generated', 'tool_invoked', 'generation_complete',
  'palette_reveal', 'palette_ready', 'font_suggestion',
];

export default function StudioScreen({ messages, phase, sendMessage, onBack, onStop, imagePreview }) {
  const scrollRef = useRef(null);
  const [input, setInput] = useState('');
  const [showOverlay, setShowOverlay] = useState(false);
  const [imageOverlay, setImageOverlay] = useState(null);

  const brandName = messages.find(m => m.type === 'brand_name_reveal')?.name
    || messages.find(m => m.type === 'brand_reveal')?.name || '';
  const tagline = messages.find(m => m.type === 'tagline_reveal')?.tagline || '';

  const completedEvents = [];
  messages.forEach(m => {
    if (m.type === 'palette_reveal' || m.type === 'palette_ready') completedEvents.push('palette_reveal');
    if (m.type === 'image_generated') completedEvents.push(`image:${m.asset_type}`);
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

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
    finalize_brand_kit: 'generation_complete',
    generate_voiceover: 'voiceover_generated',
  };
  const displayMessages = messages.filter((m, i) => {
    if (!DISPLAY_TYPES.includes(m.type)) return false;
    // Hide tool_invoked spinner if a result for this tool exists later in messages
    if (m.type === 'tool_invoked' && m.tool) {
      const resultType = TOOL_RESULT_MAP[m.tool];
      if (resultType) {
        const hasResult = messages.slice(i + 1).some(later => later.type === resultType);
        if (hasResult) return false;
      }
    }
    return true;
  });
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

          <span style={{
            fontFamily: fonts.mono, fontSize: 10, color: raw.faint,
            textTransform: 'uppercase', letterSpacing: '0.1em',
          }}>{phase || 'INIT'}</span>
        </div>

        <ProgressTracker phase={phase} completedEvents={completedEvents} />
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        flex: 1, overflow: 'auto', padding: '24px 24px 16px',
        display: 'flex', flexDirection: 'column', gap: 16,
        maxWidth: 640, width: '100%', margin: '0 auto',
      }}>
          {displayMessages.map((msg) => {
            const key = msg._id != null ? `m-${msg._id}` : `m-${msg.type}-${msg.url || msg.name || ''}`;
            if (msg.type === 'image_generated') {
              return <ImageTile key={key} msg={msg} onImageClick={handleImageClick} />;
            }
            return (
              <MessageBubble
                key={key}
                msg={msg}
                sendMessage={sendMessage}
                brandName={brandName}
                tagline={tagline}
              />
            );
          })}
      </div>

      {/* Input bar */}
      <div style={{
        padding: '0 24px 20px',
        background: `linear-gradient(to top, ${raw.cream} 60%, transparent)`,
      }}>
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
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Tell the agent what you think..."
            style={{
              flex: 1, border: 'none', background: 'transparent',
              fontSize: 14, color: raw.ink, fontFamily: fonts.body,
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
            disabled={!input.trim()}
            style={{
              width: 34, height: 34, border: 'none',
              cursor: input.trim() ? 'pointer' : 'default',
              background: input.trim() ? raw.red : raw.line,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'background 0.2s', flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke={input.trim() ? raw.white : raw.faint}
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
    </div>
  );
}
