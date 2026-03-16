import { useRef, useState, useEffect } from 'react';
import { motion } from 'motion/react';
import NameProposals from './NameProposals';
import BrandNameReveal from './BrandNameReveal';
import TaglineReveal from './TaglineReveal';
import BrandValuesPills from './BrandValuesPills';
import PaletteReveal from './PaletteReveal';
import FontSuggestion from './FontSuggestion';
import { stripMarkdown } from './StudioHelpers';
import { raw, fonts, easeCurve } from '../styles/tokens';

export { ImageTile, ProductOverlay, ImageOverlay } from './StudioHelpers';

export default function MessageBubble({ msg, sendMessage, brandName, tagline, onVoiceoverEnd, nameNarrationDone, proposalsFrozen, onStopAudio, onReset }) {
  if (msg.type === 'session_error') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '12px 0' }}
      >
        <span style={{ fontSize: 13, color: raw.muted, fontFamily: fonts.body, fontStyle: 'italic' }}>
          {msg.text}
        </span>
        {onReset && (
          <button
            onClick={onReset}
            style={{
              flexShrink: 0,
              background: 'transparent', color: raw.red,
              border: `1.5px solid ${raw.red}`, padding: '5px 16px',
              fontSize: 11, fontWeight: 700, letterSpacing: '0.15em',
              textTransform: 'uppercase', cursor: 'pointer',
              fontFamily: fonts.body,
            }}
          >
            Start Again
          </button>
        )}
      </motion.div>
    );
  }

  if (msg.type === 'agent_thinking') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 12, color: raw.faint, fontFamily: fonts.body,
          fontStyle: 'italic',
        }}
      >
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
          style={{
            width: 12, height: 12, borderRadius: '50%',
            border: `1.5px solid ${raw.red}`,
            borderTopColor: 'transparent', flexShrink: 0,
          }}
        />
        {msg.text || 'Thinking...'}
      </motion.div>
    );
  }

  if (msg.type === 'agent_narration') {
    const cleaned = stripMarkdown(msg.text);
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: easeCurve }}
        style={{
          fontSize: 15, lineHeight: 1.65, color: raw.ink,
          fontFamily: fonts.body, maxWidth: '100%',
        }}
        dangerouslySetInnerHTML={{ __html: cleaned }}
      />
    );
  }

  if (msg.type === 'agent_text') {
    const cleaned = stripMarkdown(msg.text);
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: easeCurve }}
        style={{
          fontSize: 15, lineHeight: 1.65, color: raw.ink,
          fontFamily: fonts.body, maxWidth: '100%',
        }}
      >
        <span dangerouslySetInnerHTML={{ __html: cleaned }} />
        {msg._partial && <span style={{ opacity: 0.3 }}>|</span>}
      </motion.div>
    );
  }

  if (msg.type === 'user') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          alignSelf: 'flex-end',
          background: raw.ink, color: raw.cream,
          padding: '10px 16px', fontSize: 14, lineHeight: 1.5,
          fontFamily: fonts.body, maxWidth: '80%',
        }}
      >{msg.text}</motion.div>
    );
  }

  if (msg.type === 'name_proposals' && msg.names?.length) {
    return (
      <NameProposals
        names={msg.names}
        autoSelectSeconds={msg.auto_select_seconds || 10}
        narrationDone={nameNarrationDone}
        frozen={proposalsFrozen}
        onSelect={(name) => {
          if (onStopAudio) onStopAudio();
          if (sendMessage) sendMessage({ type: 'text_input', text: `I choose ${name}` });
        }}
      />
    );
  }

  if (msg.type === 'brand_name_reveal') {
    return <BrandNameReveal name={msg.name} rationale={msg.rationale} />;
  }

  if (msg.type === 'brand_name_reveal_rationale') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          fontSize: 13, color: raw.muted, fontFamily: fonts.body,
          fontStyle: 'italic', lineHeight: 1.6, paddingLeft: 2,
        }}
      >{msg.rationale}</motion.div>
    );
  }

  if (msg.type === 'tagline_reveal') {
    return <TaglineReveal tagline={msg.tagline} />;
  }

  if (msg.type === 'brand_values') {
    return <BrandValuesPills values={msg.values} />;
  }

  if (msg.type === 'brand_story') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: easeCurve }}
        style={{
          padding: '16px 18px',
          border: `2px solid ${raw.line}`,
          background: 'rgba(255,255,255,0.4)',
        }}
      >
        <div style={{
          fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: raw.faint,
          fontFamily: fonts.body, marginBottom: 8,
        }}>BRAND STORY</div>
        <div style={{
          fontFamily: fonts.body, fontStyle: 'italic',
          fontSize: 14, lineHeight: 1.7, color: raw.muted,
        }}>{msg.story}</div>
      </motion.div>
    );
  }

  if (msg.type === 'tone_of_voice') {
    const doRules = msg.tone?.do || [];
    const dontRules = msg.tone?.dont || [];
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        style={{ padding: '16px 18px', border: `2px solid ${raw.line}`, background: 'rgba(255,255,255,0.4)' }}
      >
        <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: raw.faint, fontFamily: fonts.body, marginBottom: 12 }}>TONE OF VOICE</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {doRules.map((rule, i) => (
            <div key={`do-${i}`} style={{ fontSize: 13, color: raw.muted, display: 'flex', gap: 8 }}><span style={{ color: raw.ink, flexShrink: 0 }}>✓</span> <span>{rule}</span></div>
          ))}
          {dontRules.map((rule, i) => (
            <div key={`dont-${i}`} style={{ fontSize: 13, color: raw.muted, display: 'flex', gap: 8 }}><span style={{ color: raw.red, flexShrink: 0 }}>✗</span> <span>{rule}</span></div>
          ))}
        </div>
      </motion.div>
    );
  }

  if (msg.type === 'palette_reveal' && msg.colors?.length) {
    return <PaletteReveal colors={msg.colors} mood={msg.mood} />;
  }

  if (msg.type === 'font_suggestion') {
    return (
      <FontSuggestion
        heading={msg.heading}
        body={msg.body}
        rationale={msg.rationale}
        brandName={brandName}
        tagline={tagline}
      />
    );
  }

  if (msg.type === 'voiceover_handoff') {
    // Always render (even with no text/audio) — the component fires voiceover-handoff-ended
    // which unblocks HiddenAudio and ChatVoiceoverPlayer. Invisible when text is empty.
    return <ChatHandoffText text={msg.text} audioUrl={msg.audio_url} />;
  }

  if (msg.type === 'voiceover_greeting') {
    return msg.audio_url ? <AnnaGreetingAudio audioUrl={msg.audio_url} /> : null;
  }

  if (msg.type === 'voiceover_story' && msg.audio_url) {
    return <ChatVoiceoverPlayer audioUrl={msg.audio_url} onEnded={onVoiceoverEnd} />;
  }

  if (msg.type === 'tool_invoked') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 11, color: raw.muted, padding: '4px 0',
          fontFamily: fonts.body, textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}
      >
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          style={{
            width: 14, height: 14, borderRadius: '50%',
            border: `2px solid ${raw.red}`,
            borderTopColor: 'transparent',
          }}
        />
        {({
          generate_image: 'Creating visual',
          generate_palette: 'Building palette',
          propose_names: 'Preparing names',
          reveal_brand_identity: 'Revealing brand',
          suggest_fonts: 'Selecting typography',
          generate_voiceover: 'Recording voiceover',
          finalize_brand_kit: 'Packaging brand kit',
        }[msg.tool] || msg.tool?.replace(/_/g, ' ') || 'Working')}...
      </motion.div>
    );
  }

  if (msg.type === 'generation_complete') {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 12, fontWeight: 700, color: raw.red,
          padding: '8px 0', fontFamily: fonts.body,
          textTransform: 'uppercase', letterSpacing: '0.1em',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke={raw.red} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
        Brand kit complete
      </motion.div>
    );
  }

  return null;
}

function AnnaGreetingAudio({ audioUrl }) {
  // Hidden auto-play greeting — fires before story narration, no visible controls
  const audioRef = useRef(null);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onEnd = () => window.dispatchEvent(new CustomEvent('anna-greeting-ended'));
    const onStop = () => { a.pause(); a.currentTime = 0; };
    const onPlayNow = () => {
      window.dispatchEvent(new CustomEvent('anna-started'));
      a.play().catch(() => {
        // Autoplay blocked — skip greeting, let story start directly
        window.dispatchEvent(new CustomEvent('anna-greeting-ended'));
      });
    };
    a.addEventListener('ended', onEnd);
    window.addEventListener('voiceover-stop', onStop);
    window.addEventListener('anna-play-now', onPlayNow);
    return () => {
      a.removeEventListener('ended', onEnd);
      window.removeEventListener('voiceover-stop', onStop);
      window.removeEventListener('anna-play-now', onPlayNow);
    };
  }, []);

  return <audio ref={audioRef} src={audioUrl} preload="auto" style={{ display: 'none' }} />;
}

function ChatHandoffText({ text, audioUrl }) {
  const audioRef = useRef(null);

  useEffect(() => {
    if (!audioUrl) {
      // No handoff TTS — agent already said this via Live API.
      // Set flag so HiddenAudio can check it synchronously on mount.
      window._voiceoverHandoffDone = true;
      window.dispatchEvent(new CustomEvent('voiceover-handoff-ended'));
      return;
    }
    const a = audioRef.current;
    if (!a) return;
    const onEnd = () => window.dispatchEvent(new CustomEvent('voiceover-handoff-ended'));
    const onStop = () => { a.pause(); a.currentTime = 0; };
    a.addEventListener('ended', onEnd);
    window.addEventListener('voiceover-stop', onStop);
    a.play().catch(() => {});
    return () => { a.removeEventListener('ended', onEnd); window.removeEventListener('voiceover-stop', onStop); };
  }, [audioUrl]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: easeCurve }}
      style={{
        fontSize: 15, lineHeight: 1.65, color: raw.ink,
        fontFamily: fonts.body, padding: '4px 0',
      }}
    >
      {audioUrl && <audio ref={audioRef} src={audioUrl} preload="auto" />}
      {text || null}
    </motion.div>
  );
}

function ChatVoiceoverPlayer({ audioUrl, onEnded }) {
  const audioRef = useRef(null);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => { setCurrent(Math.floor(a.currentTime)); setProgress(a.duration ? a.currentTime / a.duration : 0); };
    const onMeta = () => setDuration(Math.floor(a.duration || 0));
    const onEnd = () => {
      setPlaying(false); setProgress(0); setCurrent(0);
      window.dispatchEvent(new CustomEvent('anna-ended'));
      if (onEnded) onEnded();
    };
    const onStop = () => {
      a.pause(); a.currentTime = 0; setPlaying(false); setProgress(0); setCurrent(0);
      window.dispatchEvent(new CustomEvent('anna-ended'));
    };
    const startStory = () => {
      // Only start if not already playing (prevents double-trigger)
      if (!a.paused) return;
      window.dispatchEvent(new CustomEvent('anna-started'));
      a.play().then(() => setPlaying(true)).catch(() => {});
    };
    // Start after greeting finishes
    const onGreetingEnded = () => startStory();
    // Start directly if no greeting exists (anna-play-now with no greeting player present)
    const onPlayNow = () => {
      // Small delay to let greeting player claim anna-play-now first
      setTimeout(() => { if (a.paused) startStory(); }, 100);
    };
    a.addEventListener('timeupdate', onTime);
    a.addEventListener('loadedmetadata', onMeta);
    a.addEventListener('ended', onEnd);
    window.addEventListener('voiceover-stop', onStop);
    window.addEventListener('anna-greeting-ended', onGreetingEnded);
    window.addEventListener('anna-play-now', onPlayNow);
    return () => {
      window.removeEventListener('voiceover-stop', onStop);
      window.removeEventListener('anna-greeting-ended', onGreetingEnded);
      window.removeEventListener('anna-play-now', onPlayNow);
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('loadedmetadata', onMeta);
      a.removeEventListener('ended', onEnd);
    };
  }, []);

  const bars = Array.from({ length: 40 }, (_, i) => ({
    height: 6 + Math.sin(i * 0.7) * 14 + Math.random() * 8,
    active: i / 40 <= progress,
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: easeCurve }}
    >
      <audio ref={audioRef} src={audioUrl} preload="metadata" />
      <div style={{
        padding: '20px 24px',
        border: '2px solid rgba(0,0,0,0.06)',
        background: 'rgba(255,255,255,0.4)',
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 8,
        }}>
          <div style={{
            fontSize: 9, fontWeight: 700, color: raw.red, letterSpacing: '0.15em',
            fontFamily: fonts.body, textTransform: 'uppercase',
          }}>BRAND STORY NARRATION</div>
          <div style={{
            fontSize: 11, color: 'rgba(0,0,0,0.25)',
            fontFamily: "'SF Mono', 'Fira Code', monospace",
          }}>{fmt(currentTime)} / {fmt(duration)}</div>
        </div>

        <div style={{ display: 'flex', gap: 2, alignItems: 'end', height: 28 }}>
          {bars.map((bar, i) => (
            <div key={i} style={{
              width: 3, borderRadius: 1,
              height: bar.height,
              background: bar.active ? raw.red : 'rgba(0,0,0,0.06)',
              transition: 'background 0.15s ease',
            }} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
