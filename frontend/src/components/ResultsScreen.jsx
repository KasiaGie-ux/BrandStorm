import { motion } from 'motion/react';
import { raw, fonts, easeCurve } from '../styles/tokens';
import Reveal from './Reveal';
import MagneticButton from './MagneticButton';
import KineticWord from './KineticWord';

function Swatch({ color, name, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: 'spring', stiffness: 100, damping: 20 }}
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}
    >
      <div style={{
        width: 48, height: 48,
        background: color,
        border: `2px solid ${raw.line}`,
      }} />
      <span style={{
        fontFamily: fonts.mono, fontSize: 10,
        color: raw.faint, textTransform: 'uppercase',
      }}>{name || color}</span>
    </motion.div>
  );
}

function ImageTile({ url, label, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ delay, duration: 0.4, ease: easeCurve }}
      style={{
        overflow: 'hidden', position: 'relative',
        border: `2px solid ${raw.line}`,
      }}
    >
      <img src={url} alt={label}
        onError={(e) => { e.currentTarget.style.display = 'none'; }}
        style={{ width: '100%', display: 'block' }} />
      <div style={{
        position: 'absolute', top: 10, left: 10,
        padding: '4px 10px', background: raw.red, color: raw.white,
        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
        fontFamily: fonts.body, textTransform: 'uppercase',
      }}>{label}</div>
    </motion.div>
  );
}

export default function ResultsScreen({ brandKit, sessionId, onReset }) {
  if (!brandKit) {
    return (
      <div style={{
        position: 'relative', zIndex: 1, minHeight: '100vh',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', padding: '40px 24px',
      }}>
        <div style={{
          padding: '48px 40px', textAlign: 'center', maxWidth: 420,
          border: `2px solid ${raw.line}`, background: 'rgba(255,255,255,0.4)',
        }}>
          <div style={{ fontSize: 15, color: raw.muted, marginBottom: 20, fontFamily: fonts.body }}>
            Something went wrong. Try again.
          </div>
          <MagneticButton onClick={onReset} style={{ padding: '14px 28px' }}>
            New Brand
          </MagneticButton>
        </div>
      </div>
    );
  }

  const assets = brandKit.asset_urls || {};
  const palette = brandKit.palette || [];
  const assetEntries = Object.entries(assets);

  return (
    <div style={{
      position: 'relative', zIndex: 1, minHeight: '100vh',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '48px 24px 60px',
    }}>
      {/* Red stripe */}
      <div style={{
        position: 'fixed', top: 0, left: 0, bottom: 0,
        width: 5, background: raw.red, zIndex: 10,
      }} />
      {/* Grid bg */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(${raw.line} 1px, transparent 1px),linear-gradient(90deg, ${raw.line} 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
      }} />

      <div style={{ maxWidth: 720, width: '100%', position: 'relative', zIndex: 3 }}>
        {/* Success badge */}
        <Reveal delay={100} from="bottom">
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            border: `2px solid ${raw.red}`, color: raw.red,
            padding: '6px 14px', fontSize: 11, fontWeight: 700,
            fontFamily: fonts.body, textTransform: 'uppercase',
            letterSpacing: '0.1em', marginBottom: 20,
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke={raw.red} strokeWidth="2.5" strokeLinecap="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            Brand Kit Complete
          </div>
        </Reveal>

        {/* Brand name */}
        <Reveal delay={200} from="bottom">
          <h1 style={{
            fontFamily: fonts.display, fontSize: 'min(12vw, 80px)',
            color: raw.ink, lineHeight: 0.9,
            textTransform: 'uppercase', letterSpacing: '0.02em',
            marginBottom: 8,
          }}>
            <KineticWord text={brandKit.brand_name || 'Your Brand'} baseDelay={300} stagger={40} from="bottom" />
          </h1>
        </Reveal>

        {/* Tagline */}
        {brandKit.tagline && (
          <Reveal delay={400} from="bottom">
            <p style={{
              fontFamily: fonts.body, fontStyle: 'italic',
              fontSize: 18, color: raw.muted, marginBottom: 12,
              borderLeft: `3px solid ${raw.red}`, paddingLeft: 16,
            }}>{brandKit.tagline}</p>
          </Reveal>
        )}

        {/* Values */}
        {brandKit.values && brandKit.values.length > 0 && (
          <Reveal delay={500} from="bottom">
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 32 }}>
              {brandKit.values.map((v, i) => (
                <span key={i} style={{
                  padding: '4px 12px',
                  border: `2px solid ${raw.red}`,
                  color: raw.red, fontSize: 11, fontWeight: 700,
                  fontFamily: fonts.body, textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                }}>{v}</span>
              ))}
            </div>
          </Reveal>
        )}

        {/* Palette */}
        {palette.length > 0 && (
          <Reveal delay={600} from="bottom">
            <div style={{
              display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 36,
            }}>
              {palette.map((c, i) => (
                <Swatch key={i} color={c.hex || c} name={c.name || c.hex || c} delay={0.65 + i * 0.05} />
              ))}
            </div>
          </Reveal>
        )}

        {/* Brand story */}
        {brandKit.story && (
          <Reveal delay={700} from="bottom">
            <div style={{
              padding: '20px 22px', marginBottom: 32,
              border: `2px solid ${raw.line}`, background: 'rgba(255,255,255,0.4)',
            }}>
              <div style={{
                fontFamily: fonts.body, fontStyle: 'italic',
                fontSize: 15, lineHeight: 1.7, color: raw.muted,
              }}>{brandKit.story}</div>
            </div>
          </Reveal>
        )}

        {/* Image grid */}
        {assetEntries.length > 0 && (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 12, marginBottom: 36,
          }}>
            {assetEntries.map(([type, url], i) => (
              <ImageTile key={type} url={url}
                label={type.replace('_', ' ')} delay={0.75 + i * 0.1} />
            ))}
          </div>
        )}

        {/* Tone of voice */}
        {brandKit.tone && (
          <Reveal delay={1000} from="bottom">
            <div style={{
              padding: '20px 22px', marginBottom: 36,
              border: `2px solid ${raw.line}`, background: 'rgba(255,255,255,0.4)',
            }}>
              <div style={{
                fontSize: 11, fontWeight: 700, color: raw.ink,
                marginBottom: 12, fontFamily: fonts.body,
                textTransform: 'uppercase', letterSpacing: '0.12em',
              }}>Tone of Voice</div>
              <div style={{ display: 'flex', gap: 24 }}>
                {brandKit.tone.do && (
                  <div style={{ flex: 1 }}>
                    {brandKit.tone.do.map((item, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 13, color: raw.ink, marginBottom: 6,
                        fontFamily: fonts.body,
                      }}>
                        <span style={{ color: raw.red, fontWeight: 700 }}>✓</span> {item}
                      </div>
                    ))}
                  </div>
                )}
                {brandKit.tone.dont && (
                  <div style={{ flex: 1 }}>
                    {brandKit.tone.dont.map((item, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 13, color: raw.ink, marginBottom: 6,
                        fontFamily: fonts.body,
                      }}>
                        <span style={{ color: raw.ink, fontWeight: 700 }}>✗</span> {item}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Reveal>
        )}

        {/* Action buttons */}
        <Reveal delay={1100} from="bottom">
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <MagneticButton onClick={onReset} style={{
              padding: '14px 28px', background: 'transparent',
              border: `2px solid ${raw.line}`, color: raw.muted,
            }}>New Brand</MagneticButton>
            {brandKit.zip_url && (
              <a href={brandKit.zip_url || `/api/download/${sessionId}`}
                style={{ textDecoration: 'none' }}>
                <MagneticButton style={{ padding: '14px 28px' }}>
                  Download ZIP
                </MagneticButton>
              </a>
            )}
          </div>
        </Reveal>
      </div>
    </div>
  );
}
