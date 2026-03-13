import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

function Pill({ value, index }) {
  return (
    <motion.span
      initial={{ opacity: 0, y: 10, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.45,
        delay: 0.15 + index * 0.1,
        ease: easeCurve,
      }}
      style={{
        display: 'inline-block',
        padding: '6px 16px',
        border: `2px solid ${raw.red}`,
        color: raw.red,
        fontSize: 10, fontWeight: 700,
        fontFamily: fonts.body, textTransform: 'uppercase',
        letterSpacing: '0.1em',
      }}
    >
      {value}
    </motion.span>
  );
}

export default function BrandValuesPills({ values = [] }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      style={{ padding: '6px 0' }}
    >
      {/* Label */}
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.4, ease: easeCurve }}
        style={{
          fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: raw.faint,
          fontFamily: fonts.body, marginBottom: 10,
        }}
      >BRAND VALUES</motion.div>

      <div style={{
        display: 'flex', gap: 8, flexWrap: 'wrap',
      }}>
        {values.map((v, i) => (
          <Pill key={i} value={v} index={i} />
        ))}
      </div>
    </motion.div>
  );
}
