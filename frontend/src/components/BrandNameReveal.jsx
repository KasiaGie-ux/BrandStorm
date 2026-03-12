import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import KineticWord from './KineticWord';
import DrawLine from './DrawLine';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function BrandNameReveal({ name, rationale }) {
  const [showLine, setShowLine] = useState(false);
  const [showTagline, setShowTagline] = useState(false);

  useEffect(() => {
    // Line appears after name animation finishes
    const lineDelay = 400 + (name?.length || 0) * 50;
    const t1 = setTimeout(() => setShowLine(true), lineDelay);
    const t2 = setTimeout(() => setShowTagline(true), lineDelay + 400);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [name]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: easeCurve }}
      style={{
        width: '100%', padding: '48px 0 32px',
        position: 'relative',
      }}
    >
      {/* Label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div style={{ width: 32, height: 1.5, background: raw.red }} />
        <span style={{
          fontSize: 9, fontWeight: 700, color: raw.red, letterSpacing: '0.2em',
          fontFamily: fonts.body, textTransform: 'uppercase',
        }}>YOUR BRAND</span>
      </div>

      {/* Brand name — HUGE kinetic */}
      <div style={{
        fontFamily: fonts.display, fontSize: 'min(18vw, 80px)',
        color: raw.ink, textTransform: 'uppercase',
        letterSpacing: '0.03em', lineHeight: 0.95,
      }}>
        <KineticWord text={name || ''} baseDelay={100} stagger={50} from="bottom" />
      </div>

      {/* Red accent line — animated across full width */}
      <div style={{
        position: 'relative', height: 3, marginTop: 14, width: '100%',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', left: 0, top: 0,
          width: showLine ? '100%' : '0%',
          height: 3,
          background: raw.red,
          transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
        }} />
      </div>

      {/* Rationale below line */}
      {rationale && (
        <div style={{
          fontFamily: fonts.body, fontStyle: 'italic',
          fontSize: 14, color: raw.muted, lineHeight: 1.6,
          marginTop: 16,
          opacity: showTagline ? 1 : 0,
          transform: showTagline ? 'translateY(0)' : 'translateY(10px)',
          transition: 'all 0.7s cubic-bezier(0.16,1,0.3,1)',
        }}>{rationale}</div>
      )}
    </motion.div>
  );
}
