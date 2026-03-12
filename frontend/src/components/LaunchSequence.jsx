import { useState, useEffect } from 'react';
import { raw, fonts } from '../styles/tokens';
import KineticWord from './KineticWord';
import DrawLine from './DrawLine';

export default function LaunchSequence({ imagePreview, firstAgentText, onComplete }) {
  const [step, setStep] = useState(0);
  const [exploded, setExploded] = useState(false);

  // Step sequencing
  useEffect(() => {
    const timers = [
      setTimeout(() => setStep(1), 300),   // image appears
      setTimeout(() => setStep(2), 600),   // voice ring
      setTimeout(() => setStep(3), 800),   // analyzing text
      setTimeout(() => setStep(4), 1500),  // ring pulses harder
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  // When first agent text arrives — explode ring
  useEffect(() => {
    if (firstAgentText && step >= 3) {
      setExploded(true);
      setStep(5);
      const t = setTimeout(() => onComplete(), 1500);
      return () => clearTimeout(t);
    }
  }, [firstAgentText, step, onComplete]);

  // Fallback: transition anyway after 5s
  useEffect(() => {
    const t = setTimeout(() => {
      if (step < 5) {
        setStep(5);
        onComplete();
      }
    }, 5000);
    return () => clearTimeout(t);
  }, [onComplete, step]);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 20,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: raw.cream,
    }}>
      {/* Grid */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `linear-gradient(${raw.line} 1px, transparent 1px),linear-gradient(90deg, ${raw.line} 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
      }} />
      {/* Red stripe */}
      <div style={{
        position: 'absolute', top: 0, left: 0, bottom: 0,
        width: 5, background: raw.red,
      }} />

      <div style={{ position: 'relative', zIndex: 3, textAlign: 'center' }}>
        {/* Product image */}
        <div style={{
          opacity: step >= 1 ? 1 : 0,
          transform: step >= 1 ? 'scale(1)' : 'scale(1.2)',
          transition: 'all 0.8s cubic-bezier(0.16,1,0.3,1)',
          marginBottom: 32,
        }}>
          {imagePreview && (
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <img src={imagePreview} alt="Product" style={{
                width: 220, height: 'auto', display: 'block',
                border: `2px solid ${raw.ink}`,
              }} />
              <div style={{
                position: 'absolute', top: 8, left: 8,
                padding: '3px 8px', background: raw.red, color: raw.white,
                fontSize: 8, fontWeight: 700, letterSpacing: '0.12em',
                fontFamily: fonts.body,
              }}>UPLOADED</div>
            </div>
          )}
        </div>

        {/* Voice ring — editorial geometric */}
        <div style={{
          opacity: step >= 2 ? 1 : 0,
          transition: 'opacity 0.5s ease',
          marginBottom: 24,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{ position: 'relative', width: 80, height: 80 }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                position: 'absolute',
                inset: i * 8,
                borderRadius: 4,
                border: `1.5px solid ${raw.red}`,
                opacity: exploded ? 0 : (step >= 4 ? 0.6 : 0.3),
                transform: exploded
                  ? `scale(${1.4 - i * 0.1})`
                  : step >= 4
                    ? `scale(${1 + i * 0.05})`
                    : 'scale(1)',
                transition: exploded
                  ? 'all 0.4s cubic-bezier(0.16,1,0.3,1)'
                  : 'all 0.6s ease',
                animation: step >= 4 && !exploded
                  ? `ringPulse 1.2s ${i * 0.15}s ease-in-out infinite`
                  : 'none',
              }} />
            ))}
          </div>
        </div>

        {/* Analyzing text */}
        <div style={{
          opacity: step >= 3 ? 1 : 0,
          transform: step >= 3 ? 'translateY(0)' : 'translateY(20px)',
          transition: 'all 0.6s cubic-bezier(0.16,1,0.3,1)',
        }}>
          {step < 5 ? (
            <>
              <div style={{
                fontSize: 12, fontWeight: 700, color: raw.muted,
                fontFamily: fonts.body, textTransform: 'uppercase',
                letterSpacing: '0.2em', marginBottom: 12,
              }}>
                {step >= 4 && !firstAgentText ? 'Connecting...' : 'Brand Architect Is Analyzing'}
              </div>
              <div style={{ position: 'relative', height: 1.5, width: 200, margin: '0 auto' }}>
                <DrawLine direction="horizontal" delay={0} color={raw.red} thickness={1.5} />
              </div>
            </>
          ) : (
            <div style={{ overflow: 'hidden', maxWidth: 500 }}>
              <div style={{
                fontFamily: fonts.display, fontSize: 36,
                textTransform: 'uppercase', letterSpacing: '0.02em',
                lineHeight: 1,
              }}>
                <KineticWord
                  text={firstAgentText?.slice(0, 40) || 'Starting session...'}
                  baseDelay={0} stagger={30} from="bottom"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes ringPulse {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.08); opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}
