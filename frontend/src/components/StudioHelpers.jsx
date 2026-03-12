import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

export function stripMarkdown(text) {
  if (!text) return '';
  let s = text;
  // Strip structured tags [TAG]...[/TAG] — these are parsed by backend, not for display
  s = s.replace(/\[([A-Z_]+)\][\s\S]*?\[\/\1\]/g, '');
  // Strip any orphaned opening/closing tags that didn't match
  s = s.replace(/\[\/[A-Z_]+\]/g, '');
  s = s.replace(/\[[A-Z_]{3,}\]/g, '');
  s = s.replace(/^#{1,6}\s+/gm, '');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  s = s.replace(/(?<!_)_([^_]+)_(?!_)/g, '<em>$1</em>');
  s = s.replace(/^\d+\.\s+/gm, '');
  s = s.replace(/^[-*]\s+/gm, '');
  s = s.replace(/\n{3,}/g, '\n\n');
  return s.trim();
}

export function resolveImageUrl(url) {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) return url;
  // In dev mode, /api/ paths go through Vite proxy automatically — no rewrite needed
  return url;
}

export function ProductOverlay({ imagePreview, onClose }) {
  if (!imagePreview) return null;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer',
      }}
    >
      <img src={imagePreview} alt="Product" style={{
        maxWidth: '80vw', maxHeight: '80vh',
        border: `2px solid ${raw.ink}`,
      }} />
      <div style={{
        position: 'absolute', top: 24, right: 24,
        width: 36, height: 36, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        background: raw.red, color: raw.white, cursor: 'pointer',
        fontSize: 18, fontWeight: 700, fontFamily: fonts.body,
      }}>✕</div>
    </motion.div>
  );
}

export function ImageOverlay({ src, label, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 60,
        background: 'rgba(10,10,10,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer', padding: 24,
      }}
    >
      <motion.img
        initial={{ scale: 0.9 }}
        animate={{ scale: 1 }}
        src={src} alt={label || 'Asset'}
        style={{
          maxWidth: '90vw', maxHeight: '85vh',
          objectFit: 'contain',
          border: `2px solid ${raw.ink}`,
        }}
      />
      <div style={{
        position: 'absolute', top: 24, right: 24,
        width: 36, height: 36, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        background: raw.red, color: raw.white, cursor: 'pointer',
        fontSize: 18, fontWeight: 700, fontFamily: fonts.body,
      }}>✕</div>
      {label && (
        <div style={{
          position: 'absolute', bottom: 24, left: '50%',
          transform: 'translateX(-50%)',
          padding: '6px 16px', background: raw.red, color: raw.white,
          fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
          fontFamily: fonts.body, textTransform: 'uppercase',
        }}>{label}</div>
      )}
    </motion.div>
  );
}

export function ImageTile({ msg, onImageClick }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const resolvedUrl = resolveImageUrl(msg.url);
  const label = msg.label || msg.asset_type?.replace(/_/g, ' ');

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeCurve }}
      style={{
        width: '100%', overflow: 'hidden', position: 'relative',
        border: `2px solid ${raw.ink}`,
        background: raw.cream,
        cursor: failed ? 'default' : 'pointer',
      }}
      onClick={() => {
        if (!failed && resolvedUrl) onImageClick(resolvedUrl, label);
      }}
    >
      {!loaded && !failed && (
        <div style={{
          width: '100%', height: 200,
          background: `linear-gradient(90deg, ${raw.line} 25%, rgba(0,0,0,0.04) 50%, ${raw.line} 75%)`,
          backgroundSize: '200% 100%',
          animation: 'shimmer 1.5s ease-in-out infinite',
        }} />
      )}

      {failed && (
        <div style={{
          width: '100%', height: 160,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 8,
          background: 'rgba(0,0,0,0.02)',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke={raw.faint} strokeWidth="1.5" strokeLinecap="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span style={{
            fontSize: 11, color: raw.faint, fontFamily: fonts.body,
          }}>Image unavailable</span>
        </div>
      )}

      {!failed && (
        <img
          src={resolvedUrl}
          alt={label || 'Generated asset'}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          style={{
            width: '100%', display: loaded ? 'block' : 'none',
            opacity: loaded ? 1 : 0,
            transition: 'opacity 0.4s ease',
          }}
        />
      )}

      <div style={{
        position: 'absolute', top: 10, left: 10,
        padding: '4px 10px', background: raw.red, color: raw.white,
        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
        fontFamily: fonts.body, textTransform: 'uppercase',
      }}>{label}</div>

      {msg.description && (
        <div style={{
          padding: '10px 14px', fontSize: 12, color: raw.muted,
          fontFamily: fonts.body, borderTop: `1px solid ${raw.line}`,
        }}>{msg.description}</div>
      )}
    </motion.div>
  );
}
