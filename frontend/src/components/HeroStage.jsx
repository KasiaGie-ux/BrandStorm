import { useState, useEffect } from 'react';
import { raw, fonts } from '../styles/tokens';
import ParallaxField from './ParallaxField';
import KineticWord from './KineticWord';
import ScrambleText from './ScrambleText';
import Marquee from './Marquee';
import MagneticButton from './MagneticButton';
import Reveal from './Reveal';

function AnimatedCounter({ target, duration = 800, delay = 0 }) {
  const [value, setValue] = useState(0);
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setStarted(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  useEffect(() => {
    if (!started) return;
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 4);
      setValue(Math.round(eased * target));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [started, target, duration]);
  return <span>{value}</span>;
}

export default function HeroStage({ onStart }) {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 200);
    return () => clearTimeout(t);
  }, []);

  return (
    <ParallaxField>
      {(mouse) => (
        <div style={{
          display: 'flex', flexDirection: 'column',
          minHeight: '100vh', padding: '40px clamp(16px, 4vw, 48px) 60px clamp(16px, 4vw, 56px)',
          justifyContent: 'center', position: 'relative',
        }}>
          {/* Grid background */}
          <div style={{ position: 'fixed', inset: 0, zIndex: 0, overflow: 'hidden', pointerEvents: 'none' }}>
            <div style={{
              position: 'absolute', inset: -20,
              backgroundImage: `linear-gradient(${raw.line} 1px, transparent 1px),linear-gradient(90deg, ${raw.line} 1px, transparent 1px)`,
              backgroundSize: '80px 80px',
              transform: `translate(${(mouse.x - 0.5) * 8}px, ${(mouse.y - 0.5) * 8}px)`,
              transition: 'transform 0.3s ease-out',
            }} />
            <div style={{
              position: 'absolute', bottom: -60, right: -20,
              fontSize: 400, fontWeight: 900, color: 'rgba(0,0,0,0.018)',
              fontFamily: fonts.display, lineHeight: 0.85,
              transform: `translate(${(mouse.x - 0.5) * -20}px, ${(mouse.y - 0.5) * -15}px)`,
              transition: 'transform 0.4s ease-out', userSelect: 'none',
            }}>60</div>
            <div style={{
              position: 'absolute', top: '12%', right: '12%',
              width: 120, height: 120,
              border: `1.5px solid ${raw.line}`,
              transform: `rotate(45deg) translate(${(mouse.x - 0.5) * -25}px, ${(mouse.y - 0.5) * -20}px)`,
              transition: 'transform 0.5s ease-out',
            }} />
            <div style={{
              position: 'absolute', top: '18%', right: '16%',
              width: 80, height: 80, borderRadius: '50%',
              border: '1.5px solid rgba(230,57,70,0.08)',
              transform: `translate(${(mouse.x - 0.5) * -15}px, ${(mouse.y - 0.5) * -12}px)`,
              transition: 'transform 0.6s ease-out',
            }} />
            <div style={{
              position: 'absolute', bottom: '25%', left: '8%',
              width: 60, height: 60, borderRadius: '50%',
              border: `1.5px solid rgba(0,0,0,0.03)`,
              transform: `translate(${(mouse.x - 0.5) * 15}px, ${(mouse.y - 0.5) * 12}px)`,
              transition: 'transform 0.5s ease-out',
            }} />
          </div>

          {/* Red accent stripe */}
          <div style={{
            position: 'fixed', top: 0, left: 0, width: 5,
            height: loaded ? '100%' : '0%',
            background: raw.red, zIndex: 10, pointerEvents: 'none',
            transition: 'height 1.2s cubic-bezier(0.16,1,0.3,1)',
            transitionDelay: '300ms',
          }} />

          {/* Top bar */}
          <div style={{
            position: 'absolute', top: 56, left: 56, right: 48,
            display: 'flex', justifyContent: 'flex-end', alignItems: 'flex-start',
            zIndex: 5,
          }}>
            <Reveal delay={800} from="right">
              <div style={{ textAlign: 'right' }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, letterSpacing: '0.2em',
                  color: raw.red, fontFamily: fonts.body, textTransform: 'uppercase',
                }}>
                  <ScrambleText text="BRANDSTORM®" />
                </div>
                <div style={{
                  fontSize: 10, color: raw.faint, marginTop: 4,
                  fontFamily: fonts.mono, letterSpacing: '0.1em',
                }}>AI CREATIVE DIRECTOR</div>
              </div>
            </Reveal>
          </div>

          {/* Main content */}
          <div style={{ maxWidth: 1000, position: 'relative', zIndex: 3 }}>
            <h1 style={{ lineHeight: 0.88, marginBottom: 36 }}>
              <div style={{
                fontSize: 'min(14vw, 140px)', fontWeight: 400,
                fontFamily: fonts.display, letterSpacing: '0.02em',
                textTransform: 'uppercase', overflow: 'hidden',
              }}>
                <KineticWord text="From" baseDelay={400} stagger={50} from="bottom" />
              </div>
              <div style={{
                fontSize: 'min(14vw, 140px)', fontWeight: 400,
                fontFamily: fonts.display, letterSpacing: '0.02em',
                textTransform: 'uppercase', overflow: 'hidden',
                WebkitTextStroke: `2px ${raw.ink}`,
                WebkitTextFillColor: 'transparent',
              }}>
                <KineticWord text="Product" baseDelay={600} stagger={45} from="bottom"
                  style={{ WebkitTextStroke: `2px ${raw.ink}`, WebkitTextFillColor: 'transparent' }} />
              </div>
              <div style={{
                fontSize: 'min(14vw, 140px)', fontWeight: 400,
                fontFamily: fonts.display, letterSpacing: '0.02em',
                textTransform: 'uppercase', overflow: 'hidden',
              }}>
                <KineticWord text="to Brand" baseDelay={850} stagger={45} from="bottom" color={raw.red} />
              </div>
            </h1>

            <div style={{
              display: 'flex', gap: 48, alignItems: 'flex-end',
              marginBottom: 24, flexWrap: 'wrap',
            }}>
              <Reveal delay={1400} from="bottom">
                <p style={{
                  fontSize: 15, color: raw.muted,
                  maxWidth: 320, lineHeight: 1.75,
                  fontFamily: fonts.body,
                  borderLeft: `3px solid ${raw.red}`, paddingLeft: 20,
                }}>
                  Upload a photo. Converse with your AI creative director.
                  Receive a complete brand identity in seconds.
                </p>
              </Reveal>

              <Reveal delay={1600} from="bottom">
                <div style={{ display: 'flex', gap: 32, fontFamily: fonts.body }}>
                  {[
                    { label: 'STRATEGY', num: 1 },
                    { label: 'IDENTITY', num: 2 },
                    { label: 'VOICE', num: 3 },
                  ].map((item) => (
                    <div key={item.label} style={{ textAlign: 'center', cursor: 'default' }}
                      onMouseEnter={e => e.currentTarget.querySelector('.num').style.color = raw.red}
                      onMouseLeave={e => e.currentTarget.querySelector('.num').style.color = raw.ink}
                    >
                      <div className="num" style={{
                        fontSize: 42, fontWeight: 400, color: raw.ink,
                        fontFamily: fonts.display,
                        transition: 'color 0.3s', letterSpacing: '0.02em',
                      }}>
                        0<AnimatedCounter target={item.num} duration={800} delay={1800 + item.num * 200} />
                      </div>
                      <div style={{
                        fontSize: 9, color: 'rgba(0,0,0,0.25)',
                        letterSpacing: '0.15em', marginTop: 2,
                      }}>
                        <ScrambleText text={item.label} />
                      </div>
                    </div>
                  ))}
                </div>
              </Reveal>
            </div>

            <Reveal delay={1800} from="bottom">
              <Marquee />
            </Reveal>

            <Reveal delay={2100} from="bottom" style={{ marginTop: 40 }}>
              <MagneticButton onClick={onStart}>
                Create Your Brand
              </MagneticButton>
            </Reveal>
          </div>

          {/* Bottom info */}
          <Reveal delay={2400} from="bottom" style={{
            position: 'absolute', bottom: 32, left: 56,
          }}>
            <div style={{
              fontSize: 10, color: raw.faint,
              fontFamily: fonts.mono, letterSpacing: '0.12em',
              display: 'flex', gap: 24,
            }}>
              <span>GEMINI LIVE AGENT</span>
              <span>·</span>
              <span>CREATIVE STORYTELLER</span>
              <span>·</span>
              <span>№ 2026</span>
            </div>
          </Reveal>
        </div>
      )}
    </ParallaxField>
  );
}
