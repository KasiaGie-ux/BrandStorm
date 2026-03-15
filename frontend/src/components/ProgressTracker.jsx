import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';

const STEPS = [
  { key: 'analysis', label: 'Analysis', phases: ['ANALYZING'] },
  { key: 'name', label: 'Name', element: 'name', phases: ['PROPOSING', 'AWAITING_INPUT'] },
  { key: 'palette', label: 'Palette', element: 'palette', events: ['palette_reveal'] },
  { key: 'logo', label: 'Logo', element: 'logo', events: ['image:logo'] },
  { key: 'hero', label: 'Hero', element: 'hero', events: ['image:hero', 'image:hero_lifestyle'] },
  { key: 'instagram', label: 'Instagram', element: 'instagram', events: ['image:instagram', 'image:instagram_post'] },
];

export default function ProgressTracker({ phase, completedEvents = [], brandCanvas }) {
  const phaseIdx = ['INIT', 'ANALYZING', 'PROPOSING', 'AWAITING_INPUT', 'GENERATING', 'REFINING', 'COMPLETE']
    .indexOf(phase || 'INIT');

  function getStepStatus(step) {
    // Canvas-first: use element status if available
    if (brandCanvas && step.element) {
      const el = brandCanvas[step.element];
      if (el) {
        if (el.status === 'ready') return 'done';
        if (el.status === 'generating') return 'active';
        if (el.status === 'stale') return 'done'; // done but needs regen
        return 'pending'; // handles 'empty' and any other status
      }
    }

    // Check event-based completion (fallback when no canvas)
    if (step.events) {
      const done = step.events.some(ev => completedEvents.includes(ev));
      if (done) return 'done';
      const inProgress = phase === 'GENERATING' || phase === 'REFINING';
      if (inProgress && !done && phaseIdx >= 4) return 'active';
      return 'pending';
    }
    // Check phase-based completion
    if (step.phases) {
      const stepPhaseIdxs = step.phases.map(p =>
        ['INIT', 'ANALYZING', 'PROPOSING', 'AWAITING_INPUT', 'GENERATING', 'REFINING', 'COMPLETE'].indexOf(p)
      );
      const maxStepPhase = Math.max(...stepPhaseIdxs);
      if (phaseIdx > maxStepPhase) return 'done';
      if (stepPhaseIdxs.includes(phaseIdx)) return 'active';
      return 'pending';
    }
    return 'pending';
  }

  return (
    <div style={{
      display: 'flex', gap: 6, padding: '8px 0',
      overflowX: 'auto', WebkitOverflowScrolling: 'touch',
      scrollbarWidth: 'none',
    }}>
      {STEPS.map((step) => {
        const status = getStepStatus(step);
        return (
          <motion.div
            key={step.key}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, ease: easeCurve }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 10px',
              fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
              fontFamily: fonts.body, textTransform: 'uppercase',
              whiteSpace: 'nowrap',
              background: status === 'done' ? raw.red : 'transparent',
              color: status === 'done' ? raw.white : status === 'active' ? raw.red : raw.faint,
              border: `1.5px solid ${status === 'done' ? raw.red : status === 'active' ? raw.red : raw.line}`,
              transition: 'all 0.3s ease',
            }}
          >
            {status === 'done' && (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                <path d="M20 6L9 17l-5-5" />
              </svg>
            )}
            {status === 'active' && (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                style={{
                  width: 10, height: 10, borderRadius: '50%',
                  border: `1.5px solid ${raw.red}`,
                  borderTopColor: 'transparent',
                }}
              />
            )}
            {status === 'pending' && (
              <div style={{
                width: 8, height: 8, borderRadius: '50%',
                border: `1.5px solid ${raw.line}`,
              }} />
            )}
            {step.label}
          </motion.div>
        );
      })}
    </div>
  );
}
