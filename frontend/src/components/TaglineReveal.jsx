import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function TaglineReveal({ tagline }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 150);
    return () => clearTimeout(t);
  }, []);

  // Split tagline into words for staggered reveal
  const words = (tagline || '').split(' ');

  return (
    <div style={{
      padding: '8px 0 12px',
      overflow: 'hidden',
    }}>
      {/* Small red dash accent */}
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: 24 }}
        transition={{ duration: 0.5, delay: 0.1, ease: easeCurve }}
        style={{ height: 1.5, background: raw.red, marginBottom: 10 }}
      />

      <div style={{
        fontFamily: fonts.body, fontStyle: 'italic',
        fontSize: 20, color: raw.muted, lineHeight: 1.5,
        letterSpacing: '0.01em',
      }}>
        {words.map((word, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 16 }}
            animate={visible ? { opacity: 1, y: 0 } : {}}
            transition={{
              duration: 0.5,
              delay: 0.2 + i * 0.08,
              ease: easeCurve,
            }}
            style={{ display: 'inline-block', marginRight: '0.3em' }}
          >
            {word}
          </motion.span>
        ))}
      </div>
    </div>
  );
}
