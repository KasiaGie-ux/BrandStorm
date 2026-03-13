import { useState, useEffect, useRef } from "react";

const RED = "#e63946";
const CREAM = "#faf6f1";
const INK = "#1a1a1a";

// ─── Kinetic Word ───
function KineticWord({ text, delay = 0, stagger = 300, size = 48 }) {
  const words = text.split(". ").filter(Boolean);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      {words.map((word, i) => (
        <KineticSingle key={i} text={word + "."} delay={delay + i * stagger} size={size} />
      ))}
    </div>
  );
}

function KineticSingle({ text, delay, size }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div style={{ overflow: "hidden", lineHeight: 1 }}>
      <div style={{
        fontSize: size,
        fontWeight: 400,
        fontFamily: "'Bebas Neue', sans-serif",
        color: INK,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        transform: visible ? "translateY(0)" : "translateY(110%)",
        opacity: visible ? 1 : 0,
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        {text}
      </div>
    </div>
  );
}

// ─── Draw Line ───
function DrawLine({ delay = 0, width = 200 }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDrawn(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return (
    <div style={{
      height: 2, background: RED, margin: "0 auto",
      width: drawn ? width : 0,
      transition: "width 0.6s cubic-bezier(0.16,1,0.3,1)",
    }} />
  );
}

// ─── Pulsing Geometric Shape ───
function GeoShape({ phase }) {
  const size = phase === "connecting" ? 80 : phase === "explode" ? 120 : 0;
  const opacity = phase === "gone" ? 0 : 1;
  const rotation = phase === "connecting" ? 45 : phase === "explode" ? 180 : 45;

  return (
    <div style={{
      width: size, height: size,
      border: `2px solid ${phase === "explode" ? RED : "rgba(0,0,0,0.08)"}`,
      transform: `rotate(${rotation}deg) scale(${phase === "explode" ? 1.3 : 1})`,
      opacity,
      transition: "all 0.8s cubic-bezier(0.16,1,0.3,1)",
      animation: phase === "connecting" ? "pulse-geo 2s ease-in-out infinite" : "none",
      margin: "0 auto",
    }} />
  );
}

// ═══════════ LAUNCH SEQUENCE ═══════════
function LaunchSequence({ productImage, onTransition }) {
  const [phase, setPhase] = useState("dimming"); // dimming → connecting → words → intro → transition
  const [dimLevel, setDimLevel] = useState(0);

  useEffect(() => {
    // Dimming
    const t1 = setTimeout(() => { setDimLevel(1); setPhase("connecting"); }, 300);
    // Words appear (simulating first agent response)
    const t2 = setTimeout(() => setPhase("words"), 2500);
    // Intro appears
    const t3 = setTimeout(() => setPhase("intro"), 4500);
    // Transition to studio
    const t4 = setTimeout(() => setPhase("transition"), 7000);
    // Done
    const t5 = setTimeout(() => onTransition?.(), 7800);
    return () => [t1, t2, t3, t4, t5].forEach(clearTimeout);
  }, []);

  const geoPhase = phase === "dimming" ? "connecting"
    : phase === "connecting" ? "connecting"
    : phase === "words" ? "explode"
    : "gone";

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      transition: "all 0.6s ease",
    }}>
      {/* Dark overlay — dims the entire screen */}
      <div style={{
        position: "absolute", inset: 0,
        background: INK,
        opacity: phase === "transition" ? 0 : dimLevel * 0.85,
        transition: "opacity 0.8s cubic-bezier(0.16,1,0.3,1)",
        zIndex: 0,
      }} />

      {/* Subtle grid visible through the darkness */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 1,
        backgroundImage: `linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)`,
        backgroundSize: "52px 52px",
        opacity: dimLevel * 0.5,
        transition: "opacity 0.8s ease",
      }} />

      {/* Red stripe — left edge */}
      <div style={{
        position: "absolute", top: 0, left: 0, bottom: 0, width: 5,
        background: RED, zIndex: 10,
        opacity: dimLevel,
        transition: "opacity 0.5s ease",
      }} />

      {/* Content */}
      <div style={{
        position: "relative", zIndex: 5,
        display: "flex", flexDirection: "column",
        alignItems: "center", gap: 0,
        opacity: phase === "transition" ? 0 : 1,
        transform: phase === "transition" ? "translateY(-30px) scale(0.95)" : "translateY(0) scale(1)",
        transition: "all 0.6s cubic-bezier(0.16,1,0.3,1)",
      }}>
        {/* Product image */}
        <div style={{
          width: 240, overflow: "hidden",
          border: `2px solid rgba(255,255,255,0.1)`,
          marginBottom: 40,
          opacity: phase === "dimming" ? 0 : 1,
          transform: phase === "dimming" ? "translateY(20px) scale(0.9)" : "translateY(0) scale(1)",
          transition: "all 0.8s cubic-bezier(0.16,1,0.3,1)",
          boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
        }}>
          <img src={productImage} alt="Product" style={{
            width: "100%", display: "block",
          }} />
          <div style={{
            position: "absolute", top: 8, left: 8,
            padding: "3px 8px", background: RED, color: "white",
            fontSize: 8, fontWeight: 700, letterSpacing: "0.1em",
            fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
          }}>UPLOADED</div>
        </div>

        {/* Geometric shape — connecting state */}
        {(phase === "dimming" || phase === "connecting") && (
          <div style={{ marginBottom: 24 }}>
            <GeoShape phase={geoPhase} />
          </div>
        )}

        {/* CONNECTING text */}
        {(phase === "dimming" || phase === "connecting") && (
          <div style={{
            fontSize: 12, fontWeight: 700, color: "rgba(255,255,255,0.3)",
            letterSpacing: "0.3em", textTransform: "uppercase",
            fontFamily: "'Syne', sans-serif",
            opacity: phase === "connecting" ? 1 : 0,
            transition: "opacity 0.5s ease",
          }}>
            CONNECTING...
          </div>
        )}

        {/* Loading line */}
        {(phase === "dimming" || phase === "connecting") && (
          <div style={{
            width: 120, height: 2, marginTop: 16,
            background: "rgba(255,255,255,0.06)",
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%", background: RED,
              animation: "loading-bar 1.5s ease-in-out infinite",
            }} />
          </div>
        )}

        {/* 3 DRAMATIC WORDS */}
        {(phase === "words" || phase === "intro" || phase === "transition") && (
          <div style={{ textAlign: "center", marginBottom: 20 }}>
            <KineticWord text="Golden. Sculpted. Iconic" delay={0} stagger={350} size={52} />
          </div>
        )}

        {/* Red line under words */}
        {(phase === "words" || phase === "intro" || phase === "transition") && (
          <div style={{ marginBottom: 28 }}>
            <DrawLine delay={1200} width={180} />
          </div>
        )}

        {/* Agent introduction */}
        {(phase === "intro" || phase === "transition") && (
          <IntroText delay={0} />
        )}
      </div>
    </div>
  );
}

function IntroText({ delay }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay + 200);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(12px)",
      transition: "all 0.7s cubic-bezier(0.16,1,0.3,1)",
      textAlign: "center",
    }}>
      <p style={{
        fontSize: 16, color: "rgba(255,255,255,0.45)",
        fontFamily: "'Syne', sans-serif", fontStyle: "italic",
        maxWidth: 400, lineHeight: 1.6, margin: "0 auto 12px",
      }}>
        I'm Charon, your creative director.
        <br />
        Let's build something extraordinary.
      </p>
      <div style={{
        fontSize: 9, color: "rgba(255,255,255,0.15)",
        fontFamily: "'Syne', sans-serif", letterSpacing: "0.2em",
        textTransform: "uppercase", marginTop: 16,
      }}>
        BRANDSTORM® · CREATIVE STORYTELLER
      </div>
    </div>
  );
}

// ═══════════ DEMO: Upload → Launch → Studio ═══════════
export default function App() {
  const [stage, setStage] = useState("upload"); // upload → launch → studio

  // Simulated product image (earrings)
  const productImg = "https://images.unsplash.com/photo-1630019852942-f89202989a59?w=400&h=500&fit=crop";

  return (
    <div style={{
      fontFamily: "'Syne', sans-serif",
      background: CREAM,
      minHeight: "100vh",
      position: "relative",
    }}>
      {/* Grid bg */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(rgba(0,0,0,0.028) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.028) 1px, transparent 1px)`,
        backgroundSize: "52px 52px",
      }} />

      {/* Red stripe */}
      <div style={{
        position: "fixed", top: 0, left: 0, bottom: 0, width: 5,
        background: RED, zIndex: 2,
      }} />

      {/* Upload state */}
      {stage === "upload" && (
        <div style={{
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          minHeight: "100vh", position: "relative", zIndex: 1,
        }}>
          <div style={{
            fontSize: 11, fontWeight: 700, color: RED,
            letterSpacing: "0.2em", fontFamily: "'Syne', sans-serif",
            textTransform: "uppercase", marginBottom: 32,
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <div style={{ width: 32, height: 1.5, background: RED }} />
            STEP 01 — THE BRIEF
          </div>

          <div style={{
            width: 300, overflow: "hidden",
            border: "2px solid rgba(0,0,0,0.07)",
            marginBottom: 32,
          }}>
            <img src={productImg} alt="Product" style={{
              width: "100%", display: "block",
            }} />
            <div style={{
              position: "relative", top: -32, left: 8,
              padding: "4px 10px", background: RED, color: "white",
              fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
              fontFamily: "'Syne', sans-serif", width: "fit-content",
            }}>UPLOADED</div>
          </div>

          <button onClick={() => setStage("launch")} style={{
            padding: "16px 40px", border: "none", cursor: "pointer",
            background: INK, color: "white",
            fontSize: 13, fontWeight: 700,
            fontFamily: "'Syne', sans-serif",
            letterSpacing: "0.1em", textTransform: "uppercase",
            borderBottom: `3px solid ${RED}`,
            transition: "all 0.3s ease",
          }}
            onMouseEnter={e => { e.currentTarget.style.background = RED; }}
            onMouseLeave={e => { e.currentTarget.style.background = INK; }}
          >
            Start Creative Session →
          </button>

          <div style={{
            marginTop: 16, fontSize: 10, color: "rgba(0,0,0,0.2)",
            fontFamily: "'Syne', sans-serif", letterSpacing: "0.08em",
          }}>🔊 BEST WITH SOUND ON</div>
        </div>
      )}

      {/* Launch Sequence */}
      {stage === "launch" && (
        <LaunchSequence
          productImage={productImg}
          onTransition={() => setStage("studio")}
        />
      )}

      {/* Studio (simplified) */}
      {stage === "studio" && (
        <div style={{
          display: "flex", flexDirection: "column",
          minHeight: "100vh", position: "relative", zIndex: 1,
          animation: "fadeIn 0.6s ease",
        }}>
          {/* Header */}
          <div style={{
            padding: "12px 24px", display: "flex", alignItems: "center", gap: 16,
            borderBottom: "1px solid rgba(0,0,0,0.06)",
            background: "rgba(250,246,241,0.9)", backdropFilter: "blur(20px)",
          }}>
            <div style={{
              width: 40, height: 40, overflow: "hidden",
              border: "2px solid rgba(0,0,0,0.08)",
            }}>
              <img src={productImg} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
            <div style={{ flex: 1, height: 3, background: "rgba(0,0,0,0.04)" }}>
              <div style={{
                height: "100%", width: "15%", background: RED,
                transition: "width 0.6s ease",
              }} />
            </div>
            <span style={{
              fontSize: 11, fontWeight: 600, color: RED,
              fontFamily: "'Syne', sans-serif",
            }}>15%</span>
          </div>

          {/* Chat */}
          <div style={{
            flex: 1, padding: "32px 48px", maxWidth: 700, margin: "0 auto", width: "100%",
          }}>
            <ChatMessage delay={0.3}>
              Gold hoops on warm wood. The sculptural curve and polished finish
              say luxury — but approachable luxury.
            </ChatMessage>

            <ChatMessage delay={1.0}>
              Going with timeless elegance — it suits the jewelry's clean lines perfectly.
            </ChatMessage>

            <div style={{ marginTop: 24, marginBottom: 8 }}>
              <ChatLabel delay={1.8} text="CHOOSE YOUR BRAND NAME" />
            </div>

            <div style={{
              display: "flex", gap: 8, marginTop: 16,
              animation: "fadeSlide 0.6s 2.2s cubic-bezier(0.16,1,0.3,1) both",
            }}>
              <NameCard name="AURIELLE" desc="Evokes golden radiance" recommended delay={2.2} />
              <NameCard name="CURVE" desc="Direct, sculptural reference" delay={2.4} />
              <NameCard name="LUMEN" desc="Light, warmth, glow" delay={2.6} />
            </div>

            <div style={{
              marginTop: 12, fontSize: 12, color: "rgba(0,0,0,0.25)",
              fontFamily: "'Syne', sans-serif", fontStyle: "italic",
              animation: "fadeSlide 0.5s 2.8s cubic-bezier(0.16,1,0.3,1) both",
            }}>
              Pick your favorite — or I'll go with my recommendation in 10s
            </div>
          </div>

          {/* Input bar */}
          <div style={{
            padding: "16px 48px", borderTop: "1px solid rgba(0,0,0,0.06)",
            display: "flex", gap: 12, alignItems: "center",
            maxWidth: 700, margin: "0 auto", width: "100%",
          }}>
            <input
              type="text" placeholder="Tell the agent what you think..."
              style={{
                flex: 1, padding: "12px 16px",
                border: "2px solid rgba(0,0,0,0.06)",
                background: "transparent", outline: "none",
                fontSize: 14, color: INK,
                fontFamily: "'Syne', sans-serif",
              }}
            />
            <button style={{
              width: 44, height: 44, background: INK, border: "none",
              color: "white", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Fonts */}
      <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Syne:wght@400;500;600;700;800&display=swap" rel="stylesheet" />

      <style>{`
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @keyframes pulse-geo {
          0%, 100% { transform: rotate(45deg) scale(1); opacity: 0.6; }
          50% { transform: rotate(45deg) scale(1.08); opacity: 1; }
        }
        @keyframes loading-bar {
          0% { width: 0%; margin-left: 0; }
          50% { width: 100%; margin-left: 0; }
          100% { width: 0%; margin-left: 100%; }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes fadeSlide {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        input::placeholder { color: rgba(0,0,0,0.25); }
      `}</style>
    </div>
  );
}

// ─── Chat Message ───
function ChatMessage({ children, delay = 0 }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay * 1000);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(10px)",
      transition: "all 0.6s cubic-bezier(0.16,1,0.3,1)",
      fontSize: 15, color: "rgba(0,0,0,0.55)", lineHeight: 1.7,
      fontFamily: "'Syne', sans-serif",
      marginBottom: 16,
    }}>
      {children}
    </div>
  );
}

// ─── Chat Label ───
function ChatLabel({ text, delay = 0 }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay * 1000);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transition: "opacity 0.5s ease",
      display: "flex", alignItems: "center", gap: 12,
    }}>
      <div style={{ width: 24, height: 1.5, background: RED }} />
      <span style={{
        fontSize: 10, fontWeight: 700, color: RED,
        letterSpacing: "0.2em", fontFamily: "'Syne', sans-serif",
      }}>{text}</span>
    </div>
  );
}

// ─── Name Card ───
function NameCard({ name, desc, recommended = false, delay = 0 }) {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay * 1000);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible
          ? (hovered ? "translateY(-3px)" : "translateY(0)")
          : "translateY(12px)",
        transition: "all 0.5s cubic-bezier(0.16,1,0.3,1)",
        flex: 1, padding: "20px 18px",
        border: `2px solid ${recommended ? RED : (hovered ? RED : "rgba(0,0,0,0.06)")}`,
        background: recommended ? "rgba(230,57,70,0.02)" : "rgba(255,255,255,0.4)",
        cursor: "pointer",
        position: "relative",
      }}
    >
      {recommended && (
        <div style={{
          position: "absolute", top: 8, right: 8,
          fontSize: 8, fontWeight: 700, color: RED,
          letterSpacing: "0.1em", fontFamily: "'Syne', sans-serif",
        }}>RECOMMENDED</div>
      )}
      <div style={{
        fontSize: 24, fontWeight: 400, color: INK,
        fontFamily: "'Bebas Neue', sans-serif",
        letterSpacing: "0.04em", marginBottom: 6,
      }}>{name}</div>
      <div style={{
        fontSize: 12, color: "rgba(0,0,0,0.35)",
        fontFamily: "'Syne', sans-serif", lineHeight: 1.4,
      }}>{desc}</div>
    </div>
  );
}
