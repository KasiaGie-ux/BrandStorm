import { useState, useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

function loadGoogleFont(family) {
  if (!family) return;
  const id = `gfont-${family.replace(/\s/g, '-')}`;
  if (document.getElementById(id)) return;
  const link = document.createElement('link');
  link.id = id;
  link.href = `https://fonts.googleapis.com/css2?family=${family.replace(/ /g, '+')}&display=swap`;
  link.rel = 'stylesheet';
  document.head.appendChild(link);
}

export default function FontSuggestion({ heading, body, rationale, brandName, tagline }) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (heading?.family) loadGoogleFont(heading.family);
    if (body?.family) loadGoogleFont(body.family);
    // Small delay to let font load
    const t = setTimeout(() => setLoaded(true), 600);
    return () => clearTimeout(t);
  }, [heading, body]);

  const sampleName = brandName || 'Your Brand';
  const sampleTagline = tagline || 'Where ideas become reality';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeCurve }}
      style={{
        width: '100%',
        background: 'rgba(255,255,255,0.5)',
        border: `2px solid ${raw.line}`,
        padding: '20px 22px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Label */}
      <div style={{
        fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: raw.faint,
        fontFamily: fonts.body, marginBottom: 16,
      }}>TYPOGRAPHY</div>

      {/* Heading font preview */}
      {heading && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontFamily: loaded ? `'${heading.family}', sans-serif` : fonts.display,
            fontSize: 36, lineHeight: 1.1, color: raw.ink,
            textTransform: 'uppercase', letterSpacing: '0.02em',
            transition: 'font-family 0.3s ease',
          }}>{sampleName}</div>
          <div style={{
            fontSize: 10, color: raw.faint, fontFamily: fonts.mono,
            marginTop: 4, letterSpacing: '0.05em',
          }}>
            {heading.family} — Heading
            {heading.style && <span style={{ color: raw.muted }}> · {heading.style}</span>}
          </div>
        </div>
      )}

      {/* Body font preview */}
      {body && (
        <div style={{ marginBottom: 14 }}>
          <div style={{
            fontFamily: loaded ? `'${body.family}', sans-serif` : fonts.body,
            fontSize: 16, lineHeight: 1.6, color: raw.muted,
            fontStyle: 'italic',
            transition: 'font-family 0.3s ease',
          }}>{sampleTagline}</div>
          <div style={{
            fontSize: 10, color: raw.faint, fontFamily: fonts.mono,
            marginTop: 4, letterSpacing: '0.05em',
          }}>
            {body.family} — Body
            {body.style && <span style={{ color: raw.muted }}> · {body.style}</span>}
          </div>
        </div>
      )}

      {/* Rationale */}
      {rationale && (
        <div style={{
          fontSize: 12, color: raw.muted, fontFamily: fonts.body,
          lineHeight: 1.5, fontStyle: 'italic',
          borderTop: `1px solid ${raw.line}`, paddingTop: 12,
        }}>{rationale}</div>
      )}
    </motion.div>
  );
}
