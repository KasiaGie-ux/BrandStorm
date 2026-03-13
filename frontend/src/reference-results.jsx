import { useState, useEffect, useRef } from "react";

const RED = "#e63946";
const CREAM = "#faf6f1";
const INK = "#1a1a1a";

// ─── Fade Up ───
function FadeUp({ children, delay = 0, style = {} }) {
  const [v, setV] = useState(false);
  useEffect(() => { const t = setTimeout(() => setV(true), delay * 1000); return () => clearTimeout(t); }, [delay]);
  return (
    <div style={{
      opacity: v ? 1 : 0, transform: v ? "translateY(0)" : "translateY(16px)",
      transition: "all 0.7s cubic-bezier(0.16,1,0.3,1)", ...style,
    }}>{children}</div>
  );
}

// ─── Draw Line ───
function DrawLine({ delay = 0, color = "rgba(0,0,0,0.08)" }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDrawn(true), delay * 1000); return () => clearTimeout(t); }, [delay]);
  return <div style={{ height: 1, background: color, width: drawn ? "100%" : "0%", transition: "width 0.8s cubic-bezier(0.16,1,0.3,1)" }} />;
}

// ─── Section Label ───
function SectionLabel({ num, text, delay = 0 }) {
  return (
    <FadeUp delay={delay}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <div style={{ width: 32, height: 1.5, background: RED }} />
        <span style={{
          fontSize: 10, fontWeight: 700, color: RED, letterSpacing: "0.2em",
          fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
        }}>{num} — {text}</span>
      </div>
    </FadeUp>
  );
}

// ─── Asset Card ───
function AssetCard({ label, gradient, aspect = "1/1", delay = 0, description }) {
  const [hovered, setHovered] = useState(false);
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <FadeUp delay={delay} style={{ cursor: "pointer" }}>
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={() => setExpanded(true)}
          style={{
            position: "relative", overflow: "hidden",
            aspectRatio: aspect, background: gradient,
            border: `2px solid ${hovered ? RED : "rgba(0,0,0,0.06)"}`,
            transition: "all 0.3s cubic-bezier(0.16,1,0.3,1)",
            transform: hovered ? "translateY(-3px)" : "translateY(0)",
            boxShadow: hovered ? "0 12px 32px rgba(0,0,0,0.08)" : "0 2px 8px rgba(0,0,0,0.03)",
          }}
        >
          <div style={{
            position: "absolute", top: 12, left: 12,
            padding: "4px 10px", background: RED, color: "white",
            fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
            fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
          }}>{label}</div>
          <div style={{
            position: "absolute", bottom: 0, left: 0, right: 0, height: "40%",
            background: "linear-gradient(to top, rgba(0,0,0,0.5), transparent)",
          }} />
          {description && (
            <div style={{
              position: "absolute", bottom: 12, left: 14, right: 14,
              fontSize: 12, color: "rgba(255,255,255,0.8)",
              fontFamily: "'Syne', sans-serif",
            }}>{description}</div>
          )}
          <div style={{
            position: "absolute", top: 12, right: 12,
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.3)", color: "white",
            opacity: hovered ? 1 : 0, transition: "opacity 0.2s",
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
          </div>
        </div>
      </FadeUp>

      {expanded && (
        <div onClick={() => setExpanded(false)} style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,0.85)",
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "zoom-out", animation: "fadeIn 0.3s ease",
        }}>
          <div style={{ width: "85vw", maxWidth: 900, aspectRatio: aspect, background: gradient, border: `2px solid ${RED}` }} />
          <button onClick={() => setExpanded(false)} style={{
            position: "absolute", top: 24, right: 24,
            background: RED, border: "none", color: "white",
            width: 36, height: 36, cursor: "pointer",
            fontSize: 18, fontWeight: 700, fontFamily: "'Syne', sans-serif",
          }}>×</button>
          <div style={{
            position: "absolute", bottom: 24, left: "50%", transform: "translateX(-50%)",
            color: "white", fontSize: 11, fontFamily: "'Syne', sans-serif",
            letterSpacing: "0.1em", textTransform: "uppercase", opacity: 0.5,
          }}>{label} — CLICK ANYWHERE TO CLOSE</div>
        </div>
      )}
    </>
  );
}

// ─── Color Swatch ───
function Swatch({ hex, name, role, delay }) {
  const [hovered, setHovered] = useState(false);
  return (
    <FadeUp delay={delay}>
      <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} style={{ textAlign: "center", cursor: "default" }}>
        <div style={{
          fontSize: 9, color: "rgba(0,0,0,0.25)", letterSpacing: "0.1em",
          fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
          marginBottom: 6, height: 14,
        }}>{role}</div>
        <div style={{
          width: 52, height: 52, background: hex,
          border: `2px solid ${hovered ? INK : "rgba(0,0,0,0.06)"}`,
          transition: "all 0.3s ease",
          transform: hovered ? "scale(1.1)" : "scale(1)", margin: "0 auto",
        }} />
        <div style={{
          fontSize: 10, color: "rgba(0,0,0,0.3)", marginTop: 6,
          fontFamily: "'SF Mono', 'Fira Code', monospace", textTransform: "uppercase",
        }}>{hex}</div>
        {hovered && name && (
          <div style={{ fontSize: 10, color: RED, marginTop: 2, fontFamily: "'Syne', sans-serif" }}>{name}</div>
        )}
      </div>
    </FadeUp>
  );
}

// ─── Font Preview ───
function FontPreview({ heading, body, brandName, tagline, delay }) {
  return (
    <FadeUp delay={delay}>
      <div style={{ padding: "28px 32px", border: "2px solid rgba(0,0,0,0.06)", background: "rgba(255,255,255,0.4)" }}>
        <div style={{
          fontSize: 10, fontWeight: 700, color: RED, letterSpacing: "0.15em",
          fontFamily: "'Syne', sans-serif", textTransform: "uppercase", marginBottom: 20,
        }}>TYPOGRAPHY</div>
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: 9, color: "rgba(0,0,0,0.25)", letterSpacing: "0.1em",
            fontFamily: "'Syne', monospace", textTransform: "uppercase", marginBottom: 6,
          }}>HEADING — {heading}</div>
          <div style={{
            fontSize: 36, fontWeight: 700, color: INK,
            fontFamily: `'${heading}', serif`, letterSpacing: "-0.02em",
          }}>{brandName}</div>
        </div>
        <DrawLine delay={delay + 0.2} />
        <div style={{ marginTop: 20 }}>
          <div style={{
            fontSize: 9, color: "rgba(0,0,0,0.25)", letterSpacing: "0.1em",
            fontFamily: "'Syne', monospace", textTransform: "uppercase", marginBottom: 6,
          }}>BODY — {body}</div>
          <div style={{
            fontSize: 16, color: "rgba(0,0,0,0.5)",
            fontFamily: `'${body}', sans-serif`, lineHeight: 1.6, fontStyle: "italic",
          }}>{tagline}</div>
        </div>
      </div>
    </FadeUp>
  );
}

// ─── Voiceover Player ───
function VoiceoverPlayer({ delay }) {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrent] = useState(0);
  const duration = 38;

  useEffect(() => {
    if (!playing) return;
    const interval = setInterval(() => {
      setProgress(p => {
        if (p >= 1) { setPlaying(false); return 0; }
        const next = p + 1 / (duration * 10);
        setCurrent(Math.floor(next * duration));
        return next;
      });
    }, 100);
    return () => clearInterval(interval);
  }, [playing]);

  const bars = Array.from({ length: 48 }, (_, i) => {
    const h = 8 + Math.sin(i * 0.45) * 10 + Math.cos(i * 0.8) * 6 + (Math.sin(i * 1.2) > 0 ? 4 : 0);
    const active = i / 48 <= progress;
    return { height: h, active };
  });

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <FadeUp delay={delay}>
      <div style={{
        padding: "24px 28px",
        border: "2px solid rgba(0,0,0,0.06)",
        background: "rgba(255,255,255,0.4)",
        display: "flex", alignItems: "center", gap: 20,
      }}>
        {/* Play/Pause */}
        <button onClick={() => setPlaying(!playing)} style={{
          width: 48, height: 48, flexShrink: 0,
          background: RED, border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.2s ease",
          boxShadow: "0 4px 12px rgba(230,57,70,0.25)",
        }}
          onMouseEnter={e => e.currentTarget.style.transform = "scale(1.05)"}
          onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
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

        {/* Waveform + info */}
        <div style={{ flex: 1 }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginBottom: 10,
          }}>
            <div style={{
              fontSize: 9, fontWeight: 700, color: RED, letterSpacing: "0.15em",
              fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
            }}>BRAND STORY</div>
            <div style={{
              fontSize: 11, color: "rgba(0,0,0,0.25)",
              fontFamily: "'SF Mono', 'Fira Code', monospace",
            }}>{fmt(currentTime)} / {fmt(duration)}</div>
          </div>

          {/* Waveform bars */}
          <div style={{
            display: "flex", gap: 2, alignItems: "end", height: 32,
            cursor: "pointer",
          }}
            onClick={e => {
              const rect = e.currentTarget.getBoundingClientRect();
              const p = (e.clientX - rect.left) / rect.width;
              setProgress(p);
              setCurrent(Math.floor(p * duration));
            }}
          >
            {bars.map((bar, i) => (
              <div key={i} style={{
                width: 3, borderRadius: 1,
                height: bar.height,
                background: bar.active
                  ? RED
                  : "rgba(0,0,0,0.06)",
                transition: "background 0.15s ease",
              }} />
            ))}
          </div>
        </div>
      </div>

      {/* Download link */}
      <div style={{
        marginTop: 8, display: "flex", justifyContent: "flex-end",
      }}>
        <a href="#" style={{
          fontSize: 10, color: "rgba(0,0,0,0.2)",
          fontFamily: "'Syne', sans-serif", letterSpacing: "0.08em",
          textTransform: "uppercase", textDecoration: "none",
          transition: "color 0.2s",
        }}
          onMouseEnter={e => e.currentTarget.style.color = RED}
          onMouseLeave={e => e.currentTarget.style.color = "rgba(0,0,0,0.2)"}
        >
          ↓ Download as WAV
        </a>
      </div>
    </FadeUp>
  );
}

// ═══════════ BRAND KIT RESULTS ═══════════
export default function App() {
  const brand = {
    name: "Vesper",
    tagline: "The quiet hour is yours.",
    story: "Vesper was born in the space between day and night — that quiet moment when you light a candle, close the door, and become entirely yours. We believe skincare is not maintenance. It's a ritual of returning to yourself.",
    values: ["Intimacy", "Intention", "Quiet Ritual"],
    palette: [
      { hex: "#2d1b3d", role: "Primary", name: "Deep Plum" },
      { hex: "#d4a574", role: "Secondary", name: "Warm Sand" },
      { hex: "#f5ede6", role: "Background", name: "Soft Cream" },
      { hex: "#8b6f5c", role: "Accent", name: "Aged Bronze" },
      { hex: "#e63946", role: "Highlight", name: "Signal Red" },
    ],
    headingFont: "Playfair Display",
    bodyFont: "Inter",
    hasVoiceover: true,
    toneOfVoice: {
      do: [
        "Speak like a close friend sharing a secret",
        "Use sensory language: warmth, texture, glow",
        "Invite, never instruct",
      ],
      dont: [
        "Never use clinical or technical language",
        "Avoid urgency words: hurry, limited, now",
        "Never compare to competitors",
      ],
    },
  };

  const [downloadHovered, setDownloadHovered] = useState(false);
  const [newHovered, setNewHovered] = useState(false);

  return (
    <div style={{ fontFamily: "'Syne', sans-serif", background: CREAM, minHeight: "100vh", position: "relative" }}>
      {/* Grid */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(rgba(0,0,0,0.025) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.025) 1px, transparent 1px)`,
        backgroundSize: "52px 52px",
      }} />

      {/* Red stripe */}
      <div style={{ position: "fixed", top: 0, left: 0, bottom: 0, width: 5, background: RED, zIndex: 10 }} />

      {/* Header */}
      <FadeUp delay={0.2}>
        <div style={{
          position: "sticky", top: 0, zIndex: 20,
          padding: "16px 56px", background: "rgba(250,246,241,0.9)",
          backdropFilter: "blur(20px)", borderBottom: "1px solid rgba(0,0,0,0.05)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div style={{
            fontSize: 11, fontWeight: 700, letterSpacing: "0.15em",
            color: INK, fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
          }}>BRANDSTORM®</div>
          <div style={{
            padding: "6px 16px", background: "rgba(5,150,105,0.08)",
            border: "1px solid rgba(5,150,105,0.15)",
            fontSize: 11, fontWeight: 600, color: "#059669", fontFamily: "'Syne', sans-serif",
          }}>✓ BRAND KIT COMPLETE</div>
        </div>
      </FadeUp>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "60px 48px 100px", position: "relative", zIndex: 1 }}>

        {/* 01 — Brand Identity */}
        <SectionLabel num="01" text="Brand Identity" delay={0.3} />
        <FadeUp delay={0.5}>
          <h1 style={{
            fontSize: 96, fontWeight: 400, color: INK,
            fontFamily: "'Bebas Neue', sans-serif",
            letterSpacing: "0.02em", textTransform: "uppercase",
            lineHeight: 0.9, marginBottom: 12,
          }}>{brand.name}</h1>
        </FadeUp>
        <FadeUp delay={0.7}>
          <p style={{
            fontSize: 22, color: "rgba(0,0,0,0.4)", fontStyle: "italic",
            marginBottom: 28, fontFamily: `'${brand.headingFont}', serif`,
          }}>{brand.tagline}</p>
        </FadeUp>
        <FadeUp delay={0.9}>
          <div style={{ display: "flex", gap: 8, marginBottom: 40 }}>
            {brand.values.map(v => (
              <span key={v} style={{
                padding: "6px 16px", border: `2px solid ${RED}`,
                fontSize: 11, fontWeight: 700, color: RED,
                letterSpacing: "0.08em", textTransform: "uppercase",
                fontFamily: "'Syne', sans-serif",
              }}>{v}</span>
            ))}
          </div>
        </FadeUp>
        <DrawLine delay={1.0} />

        {/* 02 — Brand Story */}
        <div style={{ marginTop: 48 }}>
          <SectionLabel num="02" text="Brand Story" delay={1.1} />
          <FadeUp delay={1.3}>
            <div style={{ borderLeft: `3px solid ${RED}`, paddingLeft: 24, maxWidth: 640 }}>
              <p style={{
                fontSize: 16, color: "rgba(0,0,0,0.45)", lineHeight: 1.8,
                fontStyle: "italic", fontFamily: `'${brand.headingFont}', serif`,
              }}>{brand.story}</p>
            </div>
          </FadeUp>
        </div>
        <div style={{ marginTop: 48 }}><DrawLine delay={1.4} /></div>

        {/* 03 — Color Palette */}
        <div style={{ marginTop: 48 }}>
          <SectionLabel num="03" text="Color Palette" delay={1.5} />
          <div style={{ display: "flex", gap: 28, marginTop: 8 }}>
            {brand.palette.map((c, i) => (
              <Swatch key={c.hex} {...c} delay={1.6 + i * 0.1} />
            ))}
          </div>
        </div>
        <div style={{ marginTop: 48 }}><DrawLine delay={2.0} /></div>

        {/* 04 — Typography */}
        <div style={{ marginTop: 48 }}>
          <SectionLabel num="04" text="Typography" delay={2.1} />
          <FontPreview
            heading={brand.headingFont} body={brand.bodyFont}
            brandName={brand.name} tagline={brand.tagline} delay={2.2}
          />
        </div>
        <div style={{ marginTop: 48 }}><DrawLine delay={2.4} /></div>

        {/* 05 — Visual Assets */}
        <div style={{ marginTop: 48 }}>
          <SectionLabel num="05" text="Visual Assets" delay={2.5} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 8 }}>
            <AssetCard label="Logo" description="Minimalist wordmark + crescent symbol"
              gradient="linear-gradient(135deg, #2d1b3d, #4a2d5e, #1f1128)" delay={2.6} />
            <AssetCard label="Hero Shot" description="Product in golden hour light"
              gradient="linear-gradient(135deg, #d4a574, #e8c9a8, #c49060)" delay={2.7} />
            <AssetCard label="Instagram" description="Ready to post · 1080×1350"
              gradient="linear-gradient(135deg, #3d2b4f 0%, #d4a574 50%, #2d1b3d 100%)"
              aspect="4/5" delay={2.8} />
            {/* Tone of Voice */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <FadeUp delay={2.9}>
                <div style={{
                  padding: "24px 28px", flex: 1,
                  border: "2px solid rgba(0,0,0,0.06)", background: "rgba(255,255,255,0.4)",
                }}>
                  <div style={{
                    fontSize: 10, fontWeight: 700, color: RED, letterSpacing: "0.15em",
                    textTransform: "uppercase", fontFamily: "'Syne', sans-serif", marginBottom: 16,
                  }}>TONE OF VOICE</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {brand.toneOfVoice.do.map((rule, i) => (
                      <div key={i} style={{
                        display: "flex", gap: 10, alignItems: "flex-start",
                        fontSize: 13, color: "rgba(0,0,0,0.5)", lineHeight: 1.5,
                      }}>
                        <span style={{ color: "#059669", fontWeight: 700, fontSize: 14, lineHeight: "20px" }}>✓</span>
                        {rule}
                      </div>
                    ))}
                    <div style={{ height: 1, background: "rgba(0,0,0,0.04)", margin: "4px 0" }} />
                    {brand.toneOfVoice.dont.map((rule, i) => (
                      <div key={i} style={{
                        display: "flex", gap: 10, alignItems: "flex-start",
                        fontSize: 13, color: "rgba(0,0,0,0.5)", lineHeight: 1.5,
                      }}>
                        <span style={{ color: RED, fontWeight: 700, fontSize: 14, lineHeight: "20px" }}>✗</span>
                        {rule}
                      </div>
                    ))}
                  </div>
                </div>
              </FadeUp>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 48 }}><DrawLine delay={3.1} /></div>

        {/* 06 — Voiceover */}
        {brand.hasVoiceover && (
          <div style={{ marginTop: 48 }}>
            <SectionLabel num="06" text="Voiceover" delay={3.2} />
            <VoiceoverPlayer delay={3.3} />
          </div>
        )}
        {brand.hasVoiceover && <div style={{ marginTop: 48 }}><DrawLine delay={3.6} /></div>}

        {/* Actions */}
        <div style={{ marginTop: 48, display: "flex", gap: 16, alignItems: "center" }}>
          <FadeUp delay={3.7}>
            <button
              onMouseEnter={() => setDownloadHovered(true)}
              onMouseLeave={() => setDownloadHovered(false)}
              style={{
                padding: "16px 36px", border: "none", cursor: "pointer",
                background: downloadHovered ? `linear-gradient(135deg, ${RED}, #c62828)` : INK,
                color: "white", fontSize: 13, fontWeight: 700,
                fontFamily: "'Syne', sans-serif",
                letterSpacing: "0.1em", textTransform: "uppercase",
                boxShadow: downloadHovered ? "0 8px 24px rgba(230,57,70,0.3)" : "0 4px 12px rgba(0,0,0,0.1)",
                transition: "all 0.3s cubic-bezier(0.16,1,0.3,1)",
                transform: downloadHovered ? "translateY(-2px)" : "translateY(0)",
                display: "flex", alignItems: "center", gap: 10,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download Brand Kit
            </button>
          </FadeUp>

          <FadeUp delay={3.8}>
            <button
              onMouseEnter={() => setNewHovered(true)}
              onMouseLeave={() => setNewHovered(false)}
              style={{
                padding: "16px 36px", cursor: "pointer",
                background: "transparent",
                border: `2px solid ${newHovered ? RED : "rgba(0,0,0,0.1)"}`,
                color: newHovered ? RED : "rgba(0,0,0,0.35)",
                fontSize: 13, fontWeight: 700,
                fontFamily: "'Syne', sans-serif",
                letterSpacing: "0.1em", textTransform: "uppercase",
                transition: "all 0.3s ease",
              }}
            >New Brand →</button>
          </FadeUp>

          <FadeUp delay={3.9} style={{ marginLeft: "auto" }}>
            <div style={{
              fontSize: 10, color: "rgba(0,0,0,0.15)",
              fontFamily: "'Syne', monospace", letterSpacing: "0.1em",
            }}>GENERATED BY BRANDSTORM® · {new Date().toISOString().split('T')[0]}</div>
          </FadeUp>
        </div>
      </div>

      <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Syne:wght@400;500;600;700;800&family=Playfair+Display:ital@0;1&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
      <style>{`
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}
