import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

export default function NameProposals({ names = [], autoSelectSeconds = 8, onSelect, narrationDone = false, frozen = false }) {
  const [selected, setSelected] = useState(null);
  const [countdown, setCountdown] = useState(autoSelectSeconds);
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const [visible, setVisible] = useState(false);
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

  // All cards appear at once on mount
  useEffect(() => {
    if (names.length === 0) return;
    setVisible(false);
    const t = setTimeout(() => setVisible(true), 60);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [names.length]);

  // Stop countdown immediately when user reacts
  useEffect(() => {
    if (frozen && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [frozen]);

  // Countdown starts after agent narration
  useEffect(() => {
    if (selected || names.length === 0 || !narrationDone || frozen) return;
    setCountdown(autoSelectSeconds);
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          if (!selectedRef.current && recommended) {
            selectedRef.current = recommended.name;
            queueMicrotask(() => {
              setSelected(recommended.name);
              if (onSelect) onSelect(recommended.name);
            });
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [names, selected, recommended, onSelect, narrationDone, autoSelectSeconds]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeCurve }}
      style={{ width: '100%', padding: '20px 0' }}
    >
      {/* Section label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ width: 32, height: 1.5, background: raw.red }} />
        <span style={{
          fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.2em',
          fontFamily: fonts.body, textTransform: 'uppercase',
        }}>CHOOSE YOUR BRAND NAME</span>
      </div>

      {/* Cards — all appear simultaneously */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {names.map((n, i) => {
          const isRecommended = n.recommended || (n === recommended && names.length > 0);
          const isSelected = selected === n.name;
          const isFaded = selected && !isSelected;
          const isHovered = hoveredIdx === i;

          return (
            <motion.button
              key={n.id || n.name || i}
              type="button"
              initial={{ opacity: 0, y: 28, scale: 0.97 }}
              animate={visible ? {
                opacity: isFaded ? 0.2 : 1,
                y: isHovered && !selected ? -4 : 0,
                scale: isSelected ? 1.03 : 1,
              } : { opacity: 0, y: 28, scale: 0.97 }}
              transition={visible ? {
                opacity: { duration: 0.45, ease: easeCurve, delay: i * 0.07 },
                y: { duration: 0.55, ease: easeCurve, delay: i * 0.07 },
                scale: { duration: 0.45, ease: easeCurve, delay: i * 0.07 },
              } : { duration: 0.2 }}
              onClick={() => handleSelect(n)}
              onMouseEnter={() => !selected && setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              style={{
                flex: '1 1 160px',
                minWidth: 160,
                minHeight: 160,
                background: isSelected
                  ? 'rgba(230,57,70,0.04)'
                  : isRecommended
                    ? 'rgba(230,57,70,0.03)'
                    : 'rgba(255,255,255,0.5)',
                borderTop: `2px solid ${isSelected || isHovered || isRecommended ? raw.red : 'rgba(0,0,0,0.08)'}`,
                borderRight: `2px solid ${isSelected || isHovered || isRecommended ? raw.red : 'rgba(0,0,0,0.08)'}`,
                borderBottom: `2px solid ${isSelected || isHovered || isRecommended ? raw.red : 'rgba(0,0,0,0.08)'}`,
                borderLeft: `${isRecommended || isSelected ? 4 : 2}px solid ${isRecommended || isSelected || isHovered ? raw.red : 'rgba(0,0,0,0.08)'}`,
                padding: '22px 24px',
                cursor: selected ? 'default' : 'pointer',
                textAlign: 'left',
                fontFamily: fonts.body,
                position: 'relative',
                transition: 'border-color 0.25s ease, box-shadow 0.25s ease',
                boxShadow: isHovered && !selected ? '0 8px 28px rgba(0,0,0,0.07)' : 'none',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
              }}
            >
              {/* Recommended badge */}
              {isRecommended && !selected && (
                <div style={{
                  position: 'absolute', top: 10, right: 10,
                  padding: '3px 8px',
                  background: raw.red, color: raw.white,
                  fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
                  textTransform: 'uppercase', fontFamily: fonts.body,
                }}>RECOMMENDED</div>
              )}

              {/* Selected checkmark */}
              {isSelected && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                  style={{
                    position: 'absolute', top: 10, right: 10,
                    width: 24, height: 24, background: raw.red,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                    stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </motion.div>
              )}

              {/* Name */}
              <div style={{
                fontFamily: fonts.display, fontSize: 36,
                color: raw.ink, textTransform: 'uppercase',
                lineHeight: 1.1, letterSpacing: '0.02em',
              }}>{n.name}</div>

              {/* Rationale */}
              <div style={{
                fontSize: 13, lineHeight: 1.5, color: raw.muted,
                marginTop: 12, fontFamily: fonts.body,
              }}>{n.rationale}</div>
            </motion.button>
          );
        })}
      </div>

      {/* Countdown / waiting hint */}
      <AnimatePresence>
        {!selected && !frozen && visible && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ delay: 0.4, duration: 0.4 }}
            style={{
              fontSize: 12, color: raw.red, fontFamily: fonts.body,
              marginTop: 12, fontStyle: 'italic', fontWeight: 600,
            }}
          >
            {narrationDone
              ? `Pick your favorite — or I'll go with my recommendation in ${countdown}s`
              : 'Click any name to choose — or wait for my recommendation'}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
