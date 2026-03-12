import { useState, useEffect, useRef, useCallback } from 'react';
import { raw, fonts } from '../styles/tokens';
import ParallaxField from './ParallaxField';
import KineticWord from './KineticWord';
import MagneticButton from './MagneticButton';
import Reveal from './Reveal';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_CONTEXT_CHARS = 200;

export default function UploadStage({ onBack, onGenerate, dragOnPage }) {
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [context, setContext] = useState('');
  const [showContext, setShowContext] = useState(false);
  const [entering, setEntering] = useState(false);
  const [pulseCount, setPulseCount] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const fileRef = useRef(null);
  const changeRef = useRef(null);

  useEffect(() => {
    const t = setTimeout(() => setEntering(true), 100);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    if (!isDragging) return;
    const i = setInterval(() => setPulseCount(p => p + 1), 600);
    return () => clearInterval(i);
  }, [isDragging]);

  const handleFile = useCallback((file) => {
    setUploadError(null);
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setUploadError('Unsupported format. Use PNG, JPG, or WebP.');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setUploadError('File too large. Maximum size is 10 MB.');
      return;
    }
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target.result);
    reader.onerror = () => setUploadError('Failed to read file. Please try again.');
    reader.readAsDataURL(file);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer?.files?.[0];
    handleFile(file);
  }, [handleFile]);

  const handleSubmit = useCallback(() => {
    if (!imageFile) return;
    onGenerate(imageFile, context);
  }, [imageFile, context, onGenerate]);

  const activeDrag = isDragging || dragOnPage;

  return (
    <ParallaxField>
      {(mouse) => (
        <div style={{
          display: 'flex', minHeight: '100vh', padding: '80px clamp(16px, 4vw, 48px) 60px clamp(16px, 4vw, 56px)',
          alignItems: 'center', justifyContent: 'center', position: 'relative',
          opacity: entering ? 1 : 0, transition: 'opacity 0.8s ease',
        }}>
          {/* Grid bg */}
          <div style={{
            position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
            backgroundImage: `linear-gradient(${raw.line} 1px, transparent 1px),linear-gradient(90deg, ${raw.line} 1px, transparent 1px)`,
            backgroundSize: '80px 80px',
            transform: `translate(${(mouse.x - 0.5) * 5}px, ${(mouse.y - 0.5) * 5}px)`,
            transition: 'transform 0.3s ease-out',
          }} />
          <div style={{
            position: 'fixed', top: 0, left: 0, bottom: 0,
            width: 5, background: raw.red, zIndex: 10, pointerEvents: 'none',
          }} />

          {/* Back button — fixed position so it doesn't interfere with flex layout */}
          <div style={{ position: 'absolute', top: 40, left: 56, zIndex: 15 }}>
            <Reveal delay={300} from="left">
              <BackButton onClick={onBack} />
            </Reveal>
          </div>

          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp"
            aria-label="Upload product photo" hidden
            onChange={e => handleFile(e.target.files?.[0])} />

          {/* ── EMPTY STATE: single column ── */}
          {!imageFile && (
            <div style={{
              maxWidth: 580, width: '100%', position: 'relative', zIndex: 3,
              display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
            }}>
              <Reveal delay={200} from="bottom">
                <div style={{
                  fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.25em',
                  fontFamily: fonts.body, textTransform: 'uppercase',
                  marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12,
                  justifyContent: 'center',
                }}>
                  <div style={{ width: 32, height: 1.5, background: raw.red }} />
                  Step 01 — The Brief
                  <div style={{ width: 32, height: 1.5, background: raw.red }} />
                </div>
              </Reveal>

              <div style={{ overflow: 'hidden', marginBottom: 48 }}>
                <h2 style={{
                  fontSize: 'min(10vw, 72px)', fontWeight: 400, color: raw.ink,
                  fontFamily: fonts.display, letterSpacing: '0.02em',
                  textTransform: 'uppercase', lineHeight: 0.92,
                }}>
                  <KineticWord text="Show Us" baseDelay={400} stagger={50} from="bottom" />
                  <br/>
                  <KineticWord text="Your Product" baseDelay={650} stagger={40} from="bottom" />
                </h2>
              </div>

              <Reveal delay={900} from="bottom" style={{ width: '100%' }}>
                <div
                  onClick={() => fileRef.current?.click()}
                  onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                  style={{
                    position: 'relative', minHeight: 280, width: '100%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    cursor: 'pointer',
                    border: `2px solid ${activeDrag ? raw.red : raw.line}`,
                    background: activeDrag ? 'rgba(230,57,70,0.02)' : 'rgba(255,255,255,0.3)',
                    transition: 'all 0.4s cubic-bezier(0.16,1,0.3,1)',
                    overflow: 'hidden',
                  }}
                >
                  {/* Corner brackets */}
                  {[
                    { top: 12, left: 12, bT: true, bL: true },
                    { top: 12, right: 12, bT: true, bR: true },
                    { bottom: 12, left: 12, bB: true, bL: true },
                    { bottom: 12, right: 12, bB: true, bR: true },
                  ].map((p, i) => {
                    const { bT, bR, bB, bL, ...pos } = p;
                    const c = activeDrag ? raw.red : 'rgba(0,0,0,0.1)';
                    return (
                      <div key={i} style={{
                        position: 'absolute', ...pos, width: 24, height: 24,
                        borderTop: bT ? `2px solid ${c}` : 'none',
                        borderRight: bR ? `2px solid ${c}` : 'none',
                        borderBottom: bB ? `2px solid ${c}` : 'none',
                        borderLeft: bL ? `2px solid ${c}` : 'none',
                        transition: 'border-color 0.3s',
                      }} />
                    );
                  })}

                  {activeDrag && (
                    <div style={{
                      position: 'absolute', inset: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      pointerEvents: 'none',
                    }}>
                      {[0, 1, 2].map(i => (
                        <div key={`${pulseCount}-${i}`} style={{
                          position: 'absolute',
                          width: 80 + i * 40, height: 80 + i * 40,
                          borderRadius: '50%',
                          border: `1.5px solid ${raw.red}`,
                          opacity: 0,
                          animation: `pulse 1.8s ${i * 0.3}s cubic-bezier(0.16,1,0.3,1) infinite`,
                        }} />
                      ))}
                    </div>
                  )}

                  <div style={{ textAlign: 'center', padding: '52px 32px' }}>
                    <div style={{
                      fontSize: 80, fontWeight: 400,
                      color: activeDrag ? raw.red : 'rgba(0,0,0,0.04)',
                      fontFamily: fonts.display, transition: 'all 0.4s',
                      lineHeight: 1,
                      transform: activeDrag ? 'scale(1.1)' : 'scale(1)',
                      marginBottom: 12,
                    }}>↑</div>
                    <div style={{
                      fontSize: 14, fontWeight: 700,
                      color: activeDrag ? raw.red : raw.ink,
                      fontFamily: fonts.body, textTransform: 'uppercase',
                      letterSpacing: '0.12em', marginBottom: 8,
                      transition: 'color 0.3s',
                    }}>{activeDrag ? 'Release' : 'Drop Product Photo'}</div>
                    <div style={{
                      fontSize: 12, color: raw.faint, fontFamily: fonts.body,
                    }}>or click to browse · PNG, JPG, WebP · max 10 MB</div>
                  </div>
                </div>
              </Reveal>

              {uploadError && (
                <div style={{
                  marginTop: 12, padding: '10px 16px',
                  border: `2px solid ${raw.red}`, color: raw.red,
                  fontSize: 12, fontWeight: 700, fontFamily: fonts.body,
                  letterSpacing: '0.05em', textTransform: 'uppercase',
                }}>{uploadError}</div>
              )}
            </div>
          )}

          {/* ── UPLOADED STATE: centered single column ── */}
          {imageFile && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              maxWidth: 480, width: '100%', position: 'relative', zIndex: 3,
              textAlign: 'center',
            }}>
              <Reveal delay={100} from="bottom">
                <div style={{
                  fontSize: 10, fontWeight: 700, color: raw.red, letterSpacing: '0.25em',
                  fontFamily: fonts.body, textTransform: 'uppercase',
                  marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12,
                  justifyContent: 'center',
                }}>
                  <div style={{ width: 32, height: 1.5, background: raw.red }} />
                  Ready to Create
                  <div style={{ width: 32, height: 1.5, background: raw.red }} />
                </div>
              </Reveal>

              <Reveal delay={200} from="bottom">
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <div style={{
                    position: 'relative', border: `2px solid ${raw.ink}`,
                    display: 'inline-block', maxWidth: '100%',
                  }}>
                    <input ref={changeRef} type="file" accept="image/png,image/jpeg,image/webp"
                      hidden onChange={e => handleFile(e.target.files?.[0])} />
                    <img src={imagePreview} alt="Product"
                      style={{ display: 'block', maxWidth: '100%', maxHeight: 400 }} />
                    <div style={{
                      position: 'absolute', top: 0, left: 0,
                      padding: '5px 0', width: 72, textAlign: 'center',
                      background: raw.red, color: raw.white,
                      fontSize: 8, fontWeight: 700, letterSpacing: '0.12em',
                      fontFamily: fonts.body,
                    }}>UPLOADED</div>
                    <button type="button" onClick={() => {
                      changeRef.current.value = '';
                      changeRef.current.click();
                    }} style={{
                      position: 'absolute', top: 0, right: 0,
                      padding: '5px 0', width: 72, textAlign: 'center',
                      background: raw.ink, color: raw.cream,
                      fontSize: 8, fontWeight: 700, letterSpacing: '0.12em',
                      fontFamily: fonts.body, border: 'none', cursor: 'pointer',
                      transition: 'background 0.2s, color 0.2s',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = raw.red; e.currentTarget.style.color = raw.white; }}
                      onMouseLeave={e => { e.currentTarget.style.background = raw.ink; e.currentTarget.style.color = raw.cream; }}
                    >CHANGE</button>
                  </div>
                  <button type="button" onClick={() => {
                    setImageFile(null); setImagePreview(null);
                    setUploadError(null);
                    fileRef.current.value = '';
                  }} style={{
                    marginTop: 8, background: 'none', border: 'none',
                    cursor: 'pointer', padding: 0,
                    fontSize: 10, fontWeight: 700, color: raw.faint,
                    fontFamily: fonts.body, letterSpacing: '0.1em',
                    textTransform: 'uppercase', transition: 'color 0.3s',
                  }}
                    onMouseEnter={e => e.currentTarget.style.color = raw.red}
                    onMouseLeave={e => e.currentTarget.style.color = raw.faint}
                  >REMOVE</button>
                </div>
              </Reveal>

              <Reveal delay={300} from="bottom">
                <button type="button" onClick={() => setShowContext(s => !s)} style={{
                  marginTop: 20, background: 'none', border: 'none',
                  cursor: 'pointer', padding: 0,
                  fontSize: 11, fontWeight: 700, color: raw.muted,
                  fontFamily: fonts.body, letterSpacing: '0.1em',
                  textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6,
                  transition: 'color 0.3s',
                }}
                  onMouseEnter={e => e.currentTarget.style.color = raw.red}
                  onMouseLeave={e => e.currentTarget.style.color = raw.muted}
                >
                  <span style={{
                    display: 'inline-block', transition: 'transform 0.3s',
                    transform: showContext ? 'rotate(90deg)' : 'rotate(0deg)',
                    fontSize: 10,
                  }}>▶</span>
                  Add Context (optional)
                </button>
                {showContext && (
                  <div style={{
                    marginTop: 10, padding: '14px 18px', width: '100%',
                    border: `2px solid ${context.length >= MAX_CONTEXT_CHARS ? raw.red : raw.line}`,
                    background: 'rgba(255,255,255,0.4)',
                    transition: 'border-color 0.3s', textAlign: 'left',
                  }}>
                    <textarea value={context}
                      onChange={e => {
                        if (e.target.value.length <= MAX_CONTEXT_CHARS) setContext(e.target.value);
                      }}
                      placeholder="Describe your product, audience, or desired vibe..."
                      maxLength={MAX_CONTEXT_CHARS}
                      rows={2}
                      autoFocus
                      style={{
                        width: '100%', border: 'none', background: 'transparent',
                        outline: 'none', fontSize: 13, color: raw.ink,
                        fontFamily: fonts.body, resize: 'vertical',
                        minHeight: 36, lineHeight: 1.6,
                      }}
                    />
                    <div style={{
                      textAlign: 'right', marginTop: 4,
                      fontSize: 10, fontFamily: fonts.mono,
                      letterSpacing: '0.05em',
                      color: context.length >= MAX_CONTEXT_CHARS ? raw.red : raw.faint,
                    }}>{context.length}/{MAX_CONTEXT_CHARS}</div>
                  </div>
                )}
              </Reveal>

              <Reveal delay={450} from="bottom" style={{ marginTop: 32 }}>
                <MagneticButton onClick={handleSubmit}>
                  Start Creative Session
                </MagneticButton>
                <div style={{
                  fontSize: 9, color: raw.faint, fontFamily: fonts.body,
                  textTransform: 'uppercase', letterSpacing: '0.15em',
                  marginTop: 16, opacity: 0,
                  animation: 'fadeIn 0.5s 0.4s forwards',
                }}>
                  🔊 BEST WITH SOUND ON
                </div>
              </Reveal>

              {uploadError && (
                <div style={{
                  marginTop: 16, padding: '10px 16px', width: '100%',
                  border: `2px solid ${raw.red}`, color: raw.red,
                  fontSize: 12, fontWeight: 700, fontFamily: fonts.body,
                  letterSpacing: '0.05em', textTransform: 'uppercase',
                }}>{uploadError}</div>
              )}
            </div>
          )}
        </div>
      )}
    </ParallaxField>
  );
}

function BackButton({ onClick }) {
  return (
    <button type="button" onClick={onClick} style={{
      background: 'none', border: `2px solid ${raw.line}`,
      padding: '10px 24px', cursor: 'pointer',
      fontSize: 11, fontWeight: 700, color: raw.muted,
      fontFamily: fonts.body, letterSpacing: '0.12em',
      textTransform: 'uppercase', transition: 'all 0.3s ease',
    }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = raw.red; e.currentTarget.style.color = raw.red; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = raw.line; e.currentTarget.style.color = raw.muted; }}
    >← Back</button>
  );
}
