import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import KineticWord from './KineticWord';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function BrandNameReveal({ name, rationale }) {
  const [phase, setPhase] = useState(0);
  // 0: initial flash  1: name visible  2: line drawn  3: rationale

  useEffect(() => {
    const t1 = setTimeout(() => setPhase(1), 100);
    const letterTime = (name?.length || 5) * 50 + 400;
    const t2 = setTimeout(() => setPhase(2), letterTime);
    const t3 = setTimeout(() => setPhase(3), letterTime + 500);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [name]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      style={{
        width: '100%', padding: '56px 0 36px',
        position: 'relative', overflow: 'hidden',
      }}
    >
      {/* Full-width red flash on reveal */}
      <motion.div
        initial={{ scaleX: 0, originX: 0 }}
        animate={{ scaleX: phase >= 1 ? [0, 1, 1, 0] : 0 }}
        transition={{ duration: 0.6, times: [0, 0.3, 0.7, 1], ease: 'easeInOut' }}
        style={{
          position: 'absolute', top: 0, left: -24, right: -24,
          height: '100%', background: raw.red, zIndex: 0,
          pointerEvents: 'none',
        }}
      />

      {/* Label */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={phase >= 1 ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.5, delay: 0.3, ease: easeCurve }}
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          marginBottom: 20, position: 'relative', zIndex: 1,
        }}
      >
        <div style={{ width: 40, height: 2, background: raw.red }} />
        <span style={{
          fontSize: 9, fontWeight: 700, color: raw.red, letterSpacing: '0.2em',
          fontFamily: fonts.body, textTransform: 'uppercase',
        }}>YOUR BRAND</span>
      </motion.div>

      {/* Brand name — cinematic kinetic */}
      <div style={{
        fontFamily: fonts.display, fontSize: 'min(20vw, 90px)',
        color: raw.ink, textTransform: 'uppercase',
        letterSpacing: '0.02em', lineHeight: 0.9,
        position: 'relative', zIndex: 1,
      }}>
        {phase >= 1 && (
          <KineticWord text={name || ''} baseDelay={200} stagger={60} from="bottom" />
        )}
      </div>

      {/* Red accent line — dramatic sweep */}
      <div style={{
        position: 'relative', height: 3, marginTop: 16, width: '100%',
        overflow: 'hidden',
      }}>
        <motion.div
          initial={{ scaleX: 0, originX: 0 }}
          animate={phase >= 2 ? { scaleX: 1 } : { scaleX: 0 }}
          transition={{ duration: 0.8, ease: easeCurve }}
          style={{
            position: 'absolute', left: 0, top: 0,
            width: '100%', height: 3,
            background: raw.red,
          }}
        />
      </div>

      {/* Rationale — fade in */}
      <AnimatePresence>
        {phase >= 3 && rationale && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: easeCurve }}
            style={{
              fontFamily: fonts.body, fontStyle: 'italic',
              fontSize: 14, color: raw.muted, lineHeight: 1.6,
              marginTop: 18,
            }}
          >{rationale}</motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
