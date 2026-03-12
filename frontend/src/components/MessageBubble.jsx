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

export default function MessageBubble({ msg, sendMessage, brandName, tagline }) {
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
        onSelect={(name) => {
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

  if (msg.type === 'voiceover_generated' && msg.audio_url) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: easeCurve }}
        style={{
          padding: '14px 16px',
          border: `2px solid ${raw.line}`,
          background: 'rgba(255,255,255,0.4)',
        }}
      >
        <div style={{
          fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: raw.faint,
          fontFamily: fonts.body, marginBottom: 8,
        }}>BRAND VOICEOVER</div>
        <audio controls src={msg.audio_url} style={{ width: '100%', height: 36 }} />
      </motion.div>
    );
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
        {msg.tool?.replace(/_/g, ' ') || 'Working'}...
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
