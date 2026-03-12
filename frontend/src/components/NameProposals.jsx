import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function NameProposals({ names = [], autoSelectSeconds = 10, onSelect }) {
  const [selected, setSelected] = useState(null);
  const [countdown, setCountdown] = useState(autoSelectSeconds);
  const timerRef = useRef(null);
  const selectedRef = useRef(null);

  const recommended = names.find(n => n.recommended) || names[0];

  const handleSelect = useCallback((name) => {
    if (selected) return;
    clearInterval(timerRef.current);
    setSelected(name.name);
    selectedRef.current = name.name;
    if (onSelect) onSelect(name.name);
  }, [selected, onSelect]);

  useEffect(() => {
    if (selected || names.length === 0) return;
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          if (!selectedRef.current && recommended) {
            setSelected(recommended.name);
            selectedRef.current = recommended.name;
            if (onSelect) onSelect(recommended.name);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [names, selected, recommended, onSelect]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeCurve }}
      style={{ width: '100%', padding: '8px 0' }}
    >
      {/* Cards */}
      <div style={{
        display: 'flex', gap: 10, flexWrap: 'wrap',
      }}>
        {names.map((n, i) => {
          const isRecommended = n.recommended || (n === recommended && names.length > 0);
          const isSelected = selected === n.name;
          const isFaded = selected && !isSelected;

          return (
            <motion.button
              key={n.id || i}
              type="button"
              initial={{ opacity: 0, y: 12 }}
              animate={{
                opacity: isFaded ? 0.25 : 1,
                y: 0,
                scale: isSelected ? 1.02 : 1,
              }}
              transition={{ delay: i * 0.08, duration: 0.4, ease: easeCurve }}
              onClick={() => handleSelect(n)}
              style={{
                flex: '1 1 160px',
                minWidth: 160,
                background: isSelected ? 'rgba(230,57,70,0.04)' : 'rgba(255,255,255,0.5)',
                border: `2px solid ${isSelected ? raw.red : isRecommended ? raw.red : raw.line}`,
                borderLeftWidth: isRecommended || isSelected ? 4 : 2,
                borderLeftColor: isRecommended || isSelected ? raw.red : raw.line,
                padding: '16px 18px',
                cursor: selected ? 'default' : 'pointer',
                textAlign: 'left',
                fontFamily: fonts.body,
                position: 'relative',
                transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
              }}
              onMouseEnter={e => {
                if (!selected) {
                  e.currentTarget.style.borderColor = raw.red;
                  e.currentTarget.style.background = 'rgba(230,57,70,0.03)';
                }
              }}
              onMouseLeave={e => {
                if (!selected) {
                  e.currentTarget.style.borderColor = isRecommended ? raw.red : raw.line;
                  e.currentTarget.style.background = 'rgba(255,255,255,0.5)';
                }
              }}
            >
              {/* Recommended label */}
              {isRecommended && !selected && (
                <div style={{
                  fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
                  textTransform: 'uppercase', color: raw.red,
                  marginBottom: 6, fontFamily: fonts.body,
                }}>RECOMMENDED</div>
              )}

              {/* Selected checkmark */}
              {isSelected && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  style={{
                    position: 'absolute', top: 10, right: 10,
                    width: 20, height: 20, background: raw.red,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                    stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </motion.div>
              )}

              <div style={{
                fontFamily: fonts.display, fontSize: 28,
                color: raw.ink, textTransform: 'uppercase',
                lineHeight: 1.1, letterSpacing: '0.02em',
              }}>{n.name}</div>

              <div style={{
                fontSize: 12, lineHeight: 1.5, color: raw.muted,
                marginTop: 6, fontFamily: fonts.body,
              }}>{n.rationale}</div>
            </motion.button>
          );
        })}
      </div>

      {/* Countdown */}
      <AnimatePresence>
        {!selected && countdown > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              fontSize: 11, color: raw.faint, fontFamily: fonts.body,
              marginTop: 10, fontStyle: 'italic',
            }}
          >
            Pick your favorite — or I'll go with my recommendation in {countdown}s
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
