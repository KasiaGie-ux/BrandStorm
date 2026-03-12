import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

function ColorSwatch({ color, index }) {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 150 + index * 100);
    return () => clearTimeout(t);
  }, [index]);

  const hex = color.hex || '#ccc';
  const role = color.role || '';
  const name = color.name || '';

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0) scale(1)' : 'translateY(12px) scale(0.9)',
        transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1)',
        cursor: 'default',
        position: 'relative',
      }}
    >
      {/* Role label */}
      {role && role !== 'unknown' && (
        <span style={{
          fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: raw.faint,
          fontFamily: fonts.body,
        }}>{role}</span>
      )}

      {/* Color circle */}
      <div style={{
        width: 48, height: 48, borderRadius: '50%',
        background: hex,
        boxShadow: hovered
          ? `0 4px 20px ${hex}66, 0 0 0 3px ${hex}33`
          : `0 2px 8px ${hex}33`,
        transition: 'box-shadow 0.3s ease',
        transform: hovered ? 'scale(1.1)' : 'scale(1)',
      }} />

      {/* Hex code */}
      <span style={{
        fontFamily: fonts.mono, fontSize: 9,
        color: raw.muted, textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}>{hex}</span>

      {/* Hover tooltip for name */}
      {hovered && name && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            position: 'absolute', bottom: -20,
            fontSize: 9, color: raw.ink, fontFamily: fonts.body,
            whiteSpace: 'nowrap', fontWeight: 600,
          }}
        >{name}</motion.div>
      )}
    </div>
  );
}

export default function PaletteReveal({ colors = [], mood }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: easeCurve }}
      style={{ padding: '10px 0 16px' }}
    >
      {mood && (
        <div style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: raw.faint,
          fontFamily: fonts.body, marginBottom: 10,
        }}>PALETTE — {mood}</div>
      )}
      <div style={{
        display: 'flex', gap: 20, flexWrap: 'wrap',
        alignItems: 'flex-start',
      }}>
        {colors.map((c, i) => (
          <ColorSwatch key={i} color={c} index={i} />
        ))}
      </div>
    </motion.div>
  );
}
