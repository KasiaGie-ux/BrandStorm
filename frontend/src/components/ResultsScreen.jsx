import { useState, useEffect, useRef, useCallback } from 'react';
import { raw, fonts } from '../styles/tokens';
import Reveal from './Reveal';
import MagneticButton from './MagneticButton';
import KineticWord from './KineticWord';

const EASE = 'cubic-bezier(0.16,1,0.3,1)';

// ─── FadeUp ───
function FadeUp({ children, delay = 0, style = {} }) {
  const [v, setV] = useState(false);
  useEffect(() => { const t = setTimeout(() => setV(true), delay * 1000); return () => clearTimeout(t); }, [delay]);
  return (
    <div style={{
      opacity: v ? 1 : 0, transform: v ? 'translateY(0)' : 'translateY(16px)',
      transition: `all 0.7s ${EASE}`, ...style,
    }}>{children}</div>
  );
}

// ─── DrawLine ───
function DrawLine({ delay = 0, color = 'rgba(0,0,0,0.08)' }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDrawn(true), delay * 1000); return () => clearTimeout(t); }, [delay]);
  return <div style={{ height: 1, background: color, width: drawn ? '100%' : '0%', transition: `width 0.8s ${EASE}` }} />;
}

// ─── SectionLabel ───
function SectionLabel({ num, text, delay = 0 }) {
  return (
    <FadeUp delay={delay}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ width: 32, height: 1.5, background: raw.red }} />
        <span style={{
          fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.2em',
          fontFamily: fonts.body, textTransform: 'uppercase',
        }}>{num} — {text}</span>
      </div>
    </FadeUp>
  );
}

// ─── AssetCard ───
function AssetCard({ label, url, aspect = '1/1', delay = 0, description }) {
  const [hovered, setHovered] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e) => { if (e.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  return (
    <>
      <FadeUp delay={delay} style={{ cursor: 'pointer' }}>
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={() => !errored && setExpanded(true)}
          style={{
            position: 'relative', overflow: 'hidden',
            aspectRatio: aspect,
            background: raw.cream,
            border: `2px solid ${hovered ? raw.red : 'rgba(0,0,0,0.06)'}`,
            transition: `all 0.3s ${EASE}`,
            transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
            boxShadow: hovered ? '0 12px 32px rgba(0,0,0,0.08)' : '0 2px 8px rgba(0,0,0,0.03)',
          }}
        >
          {/* Shimmer placeholder */}
          {!loaded && !errored && (
            <div style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(90deg, rgba(0,0,0,0.03) 25%, rgba(0,0,0,0.06) 50%, rgba(0,0,0,0.03) 75%)',
              backgroundSize: '200% 100%',
              animation: 'shimmer 1.5s ease-in-out infinite',
            }} />
          )}
          {errored && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 13, color: raw.muted, fontFamily: fonts.body,
            }}>Image unavailable</div>
          )}
          {url && !errored && (
            <img
              src={url}
              alt={label}
              onLoad={() => setLoaded(true)}
              onError={() => setErrored(true)}
              style={{
                width: '100%', height: '100%', objectFit: 'cover',
                display: loaded ? 'block' : 'none',
              }}
            />
          )}
          <div style={{
            position: 'absolute', top: 12, left: 12,
            padding: '4px 10px', background: raw.red, color: raw.white,
            fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
            fontFamily: fonts.body, textTransform: 'uppercase',
          }}>{label}</div>
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: '40%',
            background: 'linear-gradient(to top, rgba(0,0,0,0.5), transparent)',
          }} />
          {description && (
            <div style={{
              position: 'absolute', bottom: 12, left: 14, right: 14,
              fontSize: 12, color: 'rgba(255,255,255,0.8)',
              fontFamily: fonts.body,
            }}>{description}</div>
          )}
          <div style={{
            position: 'absolute', top: 12, right: 12,
            width: 28, height: 28,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.3)', color: 'white',
            opacity: hovered ? 1 : 0, transition: 'opacity 0.2s',
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </div>
        </div>
      </FadeUp>

      {expanded && (
        <div onClick={() => setExpanded(false)} style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.85)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'zoom-out', animation: 'fadeIn 0.3s ease',
        }}>
          <img src={url} alt={label} style={{
            maxWidth: '85vw', maxHeight: '85vh', objectFit: 'contain',
            border: `2px solid ${raw.red}`,
          }} />
          <button onClick={() => setExpanded(false)} style={{
            position: 'absolute', top: 24, right: 24,
            background: raw.red, border: 'none', color: 'white',
            width: 36, height: 36, cursor: 'pointer',
            fontSize: 18, fontWeight: 700, fontFamily: fonts.body,
          }}>x</button>
          <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            color: 'white', fontSize: 11, fontFamily: fonts.body,
            letterSpacing: '0.1em', textTransform: 'uppercase', opacity: 0.5,
          }}>{label} — CLICK ANYWHERE TO CLOSE</div>
        </div>
      )}
    </>
  );
}

// ─── Swatch ───
function Swatch({ hex, name, role, delay }) {
  const [hovered, setHovered] = useState(false);
  return (
    <FadeUp delay={delay}>
      <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} style={{ textAlign: 'center', cursor: 'default' }}>
        <div style={{
          fontSize: 9, color: 'rgba(0,0,0,0.25)', letterSpacing: '0.1em',
          fontFamily: fonts.body, textTransform: 'uppercase',
          marginBottom: 6, height: 14,
        }}>{role}</div>
        <div style={{
          width: 52, height: 52, background: hex,
          border: `2px solid ${hovered ? raw.ink : 'rgba(0,0,0,0.06)'}`,
          transition: 'all 0.3s ease',
          transform: hovered ? 'scale(1.1)' : 'scale(1)', margin: '0 auto',
        }} />
        <div style={{
          fontSize: 10, color: 'rgba(0,0,0,0.3)', marginTop: 6,
          fontFamily: "'SF Mono', 'Fira Code', monospace", textTransform: 'uppercase',
        }}>{hex}</div>
        {hovered && name && (
          <div style={{ fontSize: 10, color: raw.red, marginTop: 2, fontFamily: fonts.body }}>{name}</div>
        )}
      </div>
    </FadeUp>
  );
}

// ─── FontPreview ───
function FontPreview({ heading, body, brandName, tagline, delay }) {
  useEffect(() => {
    if (!heading && !body) return;
    const families = [heading, body].filter(Boolean).map(f => f.replace(/ /g, '+')).join('&family=');
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `https://fonts.googleapis.com/css2?family=${families}:ital,wght@0,400;0,700;1,400&display=swap`;
    document.head.appendChild(link);
    return () => document.head.removeChild(link);
  }, [heading, body]);

  return (
    <FadeUp delay={delay}>
      <div style={{ padding: '28px 32px', border: '2px solid rgba(0,0,0,0.06)', background: 'rgba(255,255,255,0.4)' }}>
        <div style={{
          fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.15em',
          fontFamily: fonts.body, textTransform: 'uppercase', marginBottom: 20,
        }}>TYPOGRAPHY</div>
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: 9, color: 'rgba(0,0,0,0.25)', letterSpacing: '0.1em',
            fontFamily: "'Syne', monospace", textTransform: 'uppercase', marginBottom: 6,
          }}>HEADING — {heading}</div>
          <div style={{
            fontSize: 36, fontWeight: 700, color: raw.ink,
            fontFamily: `'${heading}', serif`, letterSpacing: '-0.02em',
          }}>{brandName}</div>
        </div>
        <DrawLine delay={delay + 0.2} />
        <div style={{ marginTop: 20 }}>
          <div style={{
            fontSize: 9, color: 'rgba(0,0,0,0.25)', letterSpacing: '0.1em',
            fontFamily: "'Syne', monospace", textTransform: 'uppercase', marginBottom: 6,
          }}>BODY — {body}</div>
          <div style={{
            fontSize: 16, color: 'rgba(0,0,0,0.5)',
            fontFamily: `'${body}', sans-serif`, lineHeight: 1.6, fontStyle: 'italic',
          }}>{tagline}</div>
        </div>
      </div>
    </FadeUp>
  );
}

// ─── VoiceoverPlayer ───
function VoiceoverPlayer({ audioUrl, delay }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  const togglePlay = useCallback(() => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  }, [playing]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => {
      setCurrent(Math.floor(audio.currentTime));
      setProgress(audio.duration ? audio.currentTime / audio.duration : 0);
    };
    const onMeta = () => setDuration(Math.floor(audio.duration || 0));
    const onEnd = () => { setPlaying(false); setProgress(0); setCurrent(0); };
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('ended', onEnd);
    return () => {
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('ended', onEnd);
    };
  }, []);

  const bars = Array.from({ length: 48 }, (_, i) => {
    const h = 8 + Math.sin(i * 0.45) * 10 + Math.cos(i * 0.8) * 6 + (Math.sin(i * 1.2) > 0 ? 4 : 0);
    const active = i / 48 <= progress;
    return { height: h, active };
  });

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  const seekTo = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const p = (e.clientX - rect.left) / rect.width;
    if (audioRef.current && audioRef.current.duration) {
      audioRef.current.currentTime = p * audioRef.current.duration;
      setProgress(p);
      setCurrent(Math.floor(p * audioRef.current.duration));
    }
  };

  return (
    <FadeUp delay={delay}>
      <audio ref={audioRef} src={audioUrl} preload="metadata" />
      <div style={{
        padding: '24px 28px',
        border: '2px solid rgba(0,0,0,0.06)',
        background: 'rgba(255,255,255,0.4)',
        display: 'flex', alignItems: 'center', gap: 20,
      }}>
        <button onClick={togglePlay} style={{
          width: 48, height: 48, flexShrink: 0,
          background: raw.red, border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'all 0.2s ease',
          boxShadow: '0 4px 12px rgba(230,57,70,0.25)',
        }}
          onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.05)'}
          onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
        >
          {playing ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <polygon points="5,3 19,12 5,21" />
            </svg>
          )}
        </button>

        <div style={{ flex: 1 }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: 10,
          }}>
            <div style={{
              fontSize: 9, fontWeight: 700, color: raw.red, letterSpacing: '0.15em',
              fontFamily: fonts.body, textTransform: 'uppercase',
            }}>BRAND STORY</div>
            <div style={{
              fontSize: 11, color: 'rgba(0,0,0,0.25)',
              fontFamily: "'SF Mono', 'Fira Code', monospace",
            }}>{fmt(currentTime)} / {fmt(duration)}</div>
          </div>

          <div style={{
            display: 'flex', gap: 2, alignItems: 'end', height: 32,
            cursor: 'pointer',
          }} onClick={seekTo}>
            {bars.map((bar, i) => (
              <div key={i} style={{
                width: 3, borderRadius: 1,
                height: bar.height,
                background: bar.active ? raw.red : 'rgba(0,0,0,0.06)',
                transition: 'background 0.15s ease',
              }} />
            ))}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
        <a href={audioUrl} download style={{
          fontSize: 10, color: 'rgba(0,0,0,0.2)',
          fontFamily: fonts.body, letterSpacing: '0.08em',
          textTransform: 'uppercase', textDecoration: 'none',
          transition: 'color 0.2s',
        }}
          onMouseEnter={e => e.currentTarget.style.color = raw.red}
          onMouseLeave={e => e.currentTarget.style.color = 'rgba(0,0,0,0.2)'}
        >
          ↓ Download as WAV
        </a>
      </div>
    </FadeUp>
  );
}

// ═══════════ RESULTS SCREEN ═══════════
export default function ResultsScreen({ brandKit, sessionId, onReset }) {
  const [downloadHovered, setDownloadHovered] = useState(false);
  const [newHovered, setNewHovered] = useState(false);

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

  // Data extraction from brandKit payload
  const brandName = brandKit.brand_name || 'Your Brand';
  const tagline = brandKit.tagline || '';
  const brandStory = brandKit.brand_story || brandKit.story || '';
  const brandValues = brandKit.brand_values || brandKit.values || [];
  const palette = brandKit.palette || [];
  const fontSuggestion = brandKit.font_suggestion || {};
  const headingFont = fontSuggestion.heading?.family || fontSuggestion.heading || 'Playfair Display';
  const bodyFont = fontSuggestion.body?.family || fontSuggestion.body || 'Inter';
  const images = brandKit.images || [];
  const toneOfVoice = brandKit.tone_of_voice || brandKit.tone || {};
  const audioUrl = brandKit.audio_url || null;
  const zipUrl = brandKit.zip_url || `/api/download/${sessionId}`;

  // Build image map from images array or asset_urls
  const assetUrls = brandKit.asset_urls || {};
  const getImageUrl = (type) => {
    const img = images.find(i => i.asset_type === type);
    if (img) return img.url;
    return assetUrls[type] || null;
  };
  const getImageDesc = (type) => {
    const img = images.find(i => i.asset_type === type);
    return img?.description || '';
  };

  return (
    <div style={{ fontFamily: fonts.body, background: raw.cream, minHeight: '100vh', position: 'relative' }}>
      {/* Grid */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(rgba(0,0,0,0.025) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.025) 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
      }} />

      {/* Red stripe */}
      <div style={{ position: 'fixed', top: 0, left: 0, bottom: 0, width: 5, background: raw.red, zIndex: 10 }} />

      {/* Header */}
      <FadeUp delay={0.2}>
        <div style={{
          position: 'sticky', top: 0, zIndex: 20,
          padding: '16px 56px', background: 'rgba(250,246,241,0.9)',
          backdropFilter: 'blur(20px)', borderBottom: '1px solid rgba(0,0,0,0.05)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.15em',
            color: raw.ink, fontFamily: fonts.body, textTransform: 'uppercase',
          }}>BRANDSTORM®</div>
          <div style={{
            padding: '6px 16px', background: 'rgba(5,150,105,0.08)',
            border: '1px solid rgba(5,150,105,0.15)',
            fontSize: 11, fontWeight: 600, color: '#059669', fontFamily: fonts.body,
          }}>✓ BRAND KIT COMPLETE</div>
        </div>
      </FadeUp>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '60px 48px 100px', position: 'relative', zIndex: 1 }}>

        {/* 01 — Brand Identity */}
        <SectionLabel num="01" text="Brand Identity" delay={0.3} />
        <FadeUp delay={0.5}>
          <h1 style={{
            fontSize: 96, fontWeight: 400, color: raw.ink,
            fontFamily: fonts.display,
            letterSpacing: '0.02em', textTransform: 'uppercase',
            lineHeight: 0.9, marginBottom: 12,
          }}>{brandName}</h1>
        </FadeUp>
        {tagline && (
          <FadeUp delay={0.7}>
            <p style={{
              fontSize: 22, color: 'rgba(0,0,0,0.4)', fontStyle: 'italic',
              marginBottom: 28, fontFamily: `'${headingFont}', serif`,
            }}>{tagline}</p>
          </FadeUp>
        )}
        {brandValues.length > 0 && (
          <FadeUp delay={0.9}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 40 }}>
              {brandValues.map((v, i) => (
                <span key={i} style={{
                  padding: '6px 16px', border: `2px solid ${raw.red}`,
                  fontSize: 11, fontWeight: 700, color: raw.red,
                  letterSpacing: '0.08em', textTransform: 'uppercase',
                  fontFamily: fonts.body,
                  opacity: 0, animation: `fadeIn 0.5s ${EASE} ${0.9 + i * 0.1}s forwards`,
                }}>{v}</span>
              ))}
            </div>
          </FadeUp>
        )}
        <DrawLine delay={1.0} />

        {/* 02 — Brand Story */}
        {brandStory && (
          <div style={{ marginTop: 48 }}>
            <SectionLabel num="02" text="Brand Story" delay={1.1} />
            <FadeUp delay={1.3}>
              <div style={{ borderLeft: `3px solid ${raw.red}`, paddingLeft: 24, maxWidth: 640 }}>
                <p style={{
                  fontSize: 16, color: 'rgba(0,0,0,0.45)', lineHeight: 1.8,
                  fontStyle: 'italic', fontFamily: `'${headingFont}', serif`,
                }}>{brandStory}</p>
              </div>
            </FadeUp>
          </div>
        )}
        <div style={{ marginTop: 48 }}><DrawLine delay={1.4} /></div>

        {/* 03 — Color Palette */}
        {palette.length > 0 && (
          <div style={{ marginTop: 48 }}>
            <SectionLabel num="03" text="Color Palette" delay={1.5} />
            <div style={{ display: 'flex', gap: 28, marginTop: 8, flexWrap: 'wrap' }}>
              {palette.map((c, i) => (
                <Swatch key={i} hex={c.hex || c} name={c.name || ''} role={c.role || ''} delay={1.6 + i * 0.1} />
              ))}
            </div>
          </div>
        )}
        <div style={{ marginTop: 48 }}><DrawLine delay={2.0} /></div>

        {/* 04 — Typography */}
        {(headingFont || bodyFont) && (
          <div style={{ marginTop: 48 }}>
            <SectionLabel num="04" text="Typography" delay={2.1} />
            <FontPreview
              heading={headingFont} body={bodyFont}
              brandName={brandName} tagline={tagline} delay={2.2}
            />
          </div>
        )}
        <div style={{ marginTop: 48 }}><DrawLine delay={2.4} /></div>

        {/* 05 — Visual Assets + Tone of Voice */}
        <div style={{ marginTop: 48 }}>
          <SectionLabel num="05" text="Visual Assets + Tone of Voice" delay={2.5} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 8 }}>
            <AssetCard
              label="Logo"
              url={getImageUrl('logo')}
              description={getImageDesc('logo') || 'Brand logo'}
              delay={2.6}
            />
            <AssetCard
              label="Hero Shot"
              url={getImageUrl('hero_lifestyle')}
              description={getImageDesc('hero_lifestyle') || 'Hero lifestyle shot'}
              delay={2.7}
            />
            <AssetCard
              label="Instagram"
              url={getImageUrl('instagram_post')}
              description={getImageDesc('instagram_post') || 'Ready to post'}
              aspect="4/5"
              delay={2.8}
            />
            {/* Tone of Voice */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <FadeUp delay={2.9}>
                <div style={{
                  padding: '24px 28px', flex: 1,
                  border: '2px solid rgba(0,0,0,0.06)', background: 'rgba(255,255,255,0.4)',
                }}>
                  <div style={{
                    fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.15em',
                    textTransform: 'uppercase', fontFamily: fonts.body, marginBottom: 16,
                  }}>TONE OF VOICE</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {(toneOfVoice.do || []).map((rule, i) => (
                      <div key={i} style={{
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                        fontSize: 13, color: 'rgba(0,0,0,0.5)', lineHeight: 1.5,
                        fontFamily: fonts.body,
                      }}>
                        <span style={{ color: '#059669', fontWeight: 700, fontSize: 14, lineHeight: '20px' }}>✓</span>
                        {rule}
                      </div>
                    ))}
                    {(toneOfVoice.do?.length > 0 && toneOfVoice.dont?.length > 0) && (
                      <div style={{ height: 1, background: 'rgba(0,0,0,0.04)', margin: '4px 0' }} />
                    )}
                    {(toneOfVoice.dont || []).map((rule, i) => (
                      <div key={i} style={{
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                        fontSize: 13, color: 'rgba(0,0,0,0.5)', lineHeight: 1.5,
                        fontFamily: fonts.body,
                      }}>
                        <span style={{ color: raw.red, fontWeight: 700, fontSize: 14, lineHeight: '20px' }}>✗</span>
                        {rule}
                      </div>
                    ))}
                    {(!toneOfVoice.do?.length && !toneOfVoice.dont?.length) && (
                      <div style={{ fontSize: 13, color: raw.muted, fontFamily: fonts.body }}>
                        No tone guidelines available
                      </div>
                    )}
                  </div>
                </div>
              </FadeUp>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 48 }}><DrawLine delay={3.1} /></div>

        {/* 06 — Voiceover (only if audio_url exists) */}
        {audioUrl && (
          <>
            <div style={{ marginTop: 48 }}>
              <SectionLabel num="06" text="Voiceover" delay={3.2} />
              <VoiceoverPlayer audioUrl={audioUrl} delay={3.3} />
            </div>
            <div style={{ marginTop: 48 }}><DrawLine delay={3.6} /></div>
          </>
        )}

        {/* Actions */}
        <div style={{ marginTop: 48, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <FadeUp delay={3.7}>
            <a href={zipUrl} style={{ textDecoration: 'none' }}>
              <button
                onMouseEnter={() => setDownloadHovered(true)}
                onMouseLeave={() => setDownloadHovered(false)}
                style={{
                  padding: '16px 36px', border: 'none', cursor: 'pointer',
                  background: downloadHovered ? `linear-gradient(135deg, ${raw.red}, #c62828)` : raw.ink,
                  color: 'white', fontSize: 13, fontWeight: 700,
                  fontFamily: fonts.body,
                  letterSpacing: '0.1em', textTransform: 'uppercase',
                  boxShadow: downloadHovered ? '0 8px 24px rgba(230,57,70,0.3)' : '0 4px 12px rgba(0,0,0,0.1)',
                  transition: `all 0.3s ${EASE}`,
                  transform: downloadHovered ? 'translateY(-2px)' : 'translateY(0)',
                  display: 'flex', alignItems: 'center', gap: 10,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download Brand Kit
              </button>
            </a>
          </FadeUp>

          <FadeUp delay={3.8}>
            <button
              onClick={onReset}
              onMouseEnter={() => setNewHovered(true)}
              onMouseLeave={() => setNewHovered(false)}
              style={{
                padding: '16px 36px', cursor: 'pointer',
                background: 'transparent',
                border: `2px solid ${newHovered ? raw.red : 'rgba(0,0,0,0.1)'}`,
                color: newHovered ? raw.red : 'rgba(0,0,0,0.35)',
                fontSize: 13, fontWeight: 700,
                fontFamily: fonts.body,
                letterSpacing: '0.1em', textTransform: 'uppercase',
                transition: 'all 0.3s ease',
              }}
            >New Brand →</button>
          </FadeUp>

          <FadeUp delay={3.9} style={{ marginLeft: 'auto' }}>
            <div style={{
              fontSize: 10, color: 'rgba(0,0,0,0.15)',
              fontFamily: "'Syne', monospace", letterSpacing: '0.1em',
            }}>GENERATED BY BRANDSTORM® · {new Date().toISOString().split('T')[0]}</div>
          </FadeUp>
        </div>
      </div>

      <style>{`
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}
