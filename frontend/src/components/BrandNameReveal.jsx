import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import KineticWord from './KineticWord';
import DrawLine from './DrawLine';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function BrandNameReveal({ name, rationale }) {
  const [showRationale, setShowRationale] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowRationale(true), 600 + (name?.length || 0) * 40);
    return () => clearTimeout(t);
  }, [name]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: easeCurve }}
      style={{
        width: '100%', padding: '28px 0 20px',
        position: 'relative',
      }}
    >
      {/* Brand name — huge kinetic */}
      <div style={{
        fontFamily: fonts.display, fontSize: 'min(14vw, 64px)',
        color: raw.ink, textTransform: 'uppercase',
        letterSpacing: '0.03em', lineHeight: 1,
      }}>
        <KineticWord text={name || ''} baseDelay={100} stagger={50} from="bottom" />
      </div>

      {/* Red accent line */}
      <div style={{ position: 'relative', height: 3, marginTop: 10, width: '100%' }}>
        <DrawLine direction="horizontal" delay={400} color={raw.red} thickness={3} />
      </div>

      {/* Rationale */}
      {rationale && (
        <div style={{
          fontFamily: fonts.body, fontStyle: 'italic',
          fontSize: 13, color: raw.muted, lineHeight: 1.6,
          marginTop: 14,
          opacity: showRationale ? 1 : 0,
          transform: showRationale ? 'translateY(0)' : 'translateY(8px)',
          transition: 'all 0.6s cubic-bezier(0.16,1,0.3,1)',
        }}>{rationale}</div>
      )}
    </motion.div>
  );
}
