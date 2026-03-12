import { useState, useEffect, useRef, useCallback } from "react";

// ═══════════════════════════════════════════════════
// BRANDSTORM — EDITORIAL SWISS (WOW EDITION)
// ═══════════════════════════════════════════════════

const RED = "#e63946";
const CREAM = "#faf6f1";
const INK = "#1a1a1a";

// ─── KINETIC LETTER (slides in individually) ───
function KineticLetter({ char, delay, from = "bottom", color = INK, style = {} }) {
  const [v, setV] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setV(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  const origins = {
    bottom: { from: "translateY(110%) rotateX(-40deg)", to: "translateY(0) rotateX(0)" },
    top: { from: "translateY(-110%) rotateX(40deg)", to: "translateY(0) rotateX(0)" },
    left: { from: "translateX(-80px) rotateZ(-10deg)", to: "translateX(0) rotateZ(0)" },
    right: { from: "translateX(80px) rotateZ(10deg)", to: "translateX(0) rotateZ(0)" },
  };

  return (
    <span style={{
      display: "inline-block",
      overflow: "hidden",
      perspective: 400,
      verticalAlign: "top",
    }}>
      <span style={{
        display: "inline-block",
        transform: v ? origins[from].to : origins[from].from,
        opacity: v ? 1 : 0,
        transition: `transform 0.8s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.5s ease`,
        transitionDelay: "0ms",
        color,
        ...style,
      }}>
        {char === " " ? "\u00A0" : char}
      </span>
    </span>
  );
}

// ─── KINETIC WORD ───
function KineticWord({ text, baseDelay = 0, stagger = 40, from = "bottom", color = INK, style = {} }) {
  return (
    <span>
      {text.split("").map((ch, i) => (
        <KineticLetter key={i} char={ch} delay={baseDelay + i * stagger}
          from={from} color={color} style={style} />
      ))}
    </span>
  );
}

// ─── TEXT SCRAMBLE on hover ───
function ScrambleText({ text, style = {} }) {
  const [display, setDisplay] = useState(text);
  const [isScrambling, setIsScrambling] = useState(false);
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&";

  const scramble = useCallback(() => {
    if (isScrambling) return;
    setIsScrambling(true);
    let iteration = 0;
    const interval = setInterval(() => {
      setDisplay(text.split("").map((ch, i) => {
        if (ch === " ") return " ";
        if (i < iteration) return text[i];
        return chars[Math.floor(Math.random() * chars.length)];
      }).join(""));
      iteration += 1 / 2;
      if (iteration >= text.length) {
        clearInterval(interval);
        setDisplay(text);
        setIsScrambling(false);
      }
    }, 30);
  }, [text, isScrambling]);

  return (
    <span
      onMouseEnter={scramble}
      style={{ cursor: "default", ...style }}
    >{display}</span>
  );
}

// ─── ANIMATED LINE (draws itself) ───
function DrawLine({ direction = "vertical", delay = 0, color = "rgba(0,0,0,0.06)", thickness = 1 }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDrawn(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  const isV = direction === "vertical";
  return (
    <div style={{
      position: "absolute",
      [isV ? "width" : "height"]: thickness,
      [isV ? "height" : "width"]: drawn ? "100%" : "0%",
      background: color,
      transition: `all 1.2s cubic-bezier(0.16, 1, 0.3, 1)`,
      transitionDelay: `${delay}ms`,
    }} />
  );
}

// ─── MAGNETIC BUTTON ───
function MagneticButton({ children, onClick, style = {} }) {
  const ref = useRef(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);

  const handleMove = (e) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const x = (e.clientX - rect.left - rect.width / 2) * 0.25;
    const y = (e.clientY - rect.top - rect.height / 2) * 0.25;
    setOffset({ x, y });
  };

  return (
    <div
      ref={ref}
      onMouseMove={handleMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setOffset({ x: 0, y: 0 }); }}
      onClick={onClick}
      style={{
        display: "inline-block",
        transform: `translate(${offset.x}px, ${offset.y}px)`,
        transition: hovered ? "transform 0.15s ease-out" : "transform 0.5s cubic-bezier(0.16,1,0.3,1)",
        cursor: "pointer",
      }}
    >
      <div style={{
        padding: "22px 52px",
        border: `2px solid ${INK}`,
        background: hovered ? INK : "transparent",
        color: hovered ? CREAM : INK,
        fontSize: 13, fontWeight: 700,
        fontFamily: "'Syne', sans-serif",
        letterSpacing: "0.18em", textTransform: "uppercase",
        transition: "all 0.3s ease",
        display: "flex", alignItems: "center", gap: 16,
        position: "relative", overflow: "hidden",
        ...style,
      }}>
        {/* Sweep fill effect */}
        <div style={{
          position: "absolute", inset: 0,
          background: INK,
          transform: hovered ? "translateX(0)" : "translateX(-101%)",
          transition: "transform 0.4s cubic-bezier(0.16,1,0.3,1)",
          zIndex: 0,
        }} />
        <span style={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", gap: 16 }}>
          {children}
          <span style={{
            display: "inline-block",
            transition: "transform 0.3s cubic-bezier(0.16,1,0.3,1)",
            transform: hovered ? "translateX(8px)" : "translateX(0)",
            fontSize: 18,
          }}>→</span>
        </span>
      </div>
    </div>
  );
}

// ─── REVEAL with stagger ───
function Reveal({ children, delay = 0, from = "bottom", style = {} }) {
  const [v, setV] = useState(false);
  useEffect(() => { const t = setTimeout(() => setV(true), delay); return () => clearTimeout(t); }, [delay]);
  const transforms = {
    bottom: v ? "translateY(0)" : "translateY(50px)",
    left: v ? "translateX(0)" : "translateX(-50px)",
    right: v ? "translateX(0)" : "translateX(50px)",
    scale: v ? "scale(1)" : "scale(0.85)",
  };
  return (
    <div style={{
      opacity: v ? 1 : 0, transform: transforms[from],
      transition: "all 0.9s cubic-bezier(0.16,1,0.3,1)", ...style,
    }}>{children}</div>
  );
}

// ─── ROTATING CIRCLE TEXT ───
function RotatingBadge({ text = "BRAND STORM · AI CREATIVE · ", size = 100 }) {
  return (
    <div style={{
      width: size, height: size, position: "relative",
      animation: "spin 12s linear infinite",
    }}>
      <svg viewBox="0 0 100 100" style={{ width: "100%", height: "100%" }}>
        <defs>
          <path id="circlePath" d="M 50, 50 m -37, 0 a 37,37 0 1,1 74,0 a 37,37 0 1,1 -74,0" />
        </defs>
        <text style={{ fontSize: 9.5, letterSpacing: "0.22em", fill: "rgba(0,0,0,0.2)", fontFamily: "'Syne', sans-serif", fontWeight: 600, textTransform: "uppercase" }}>
          <textPath href="#circlePath">{text}{text}</textPath>
        </text>
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={RED} strokeWidth="2.5" strokeLinecap="round">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
        </svg>
      </div>
    </div>
  );
}

// ─── MARQUEE TICKER ───
function Marquee() {
  const items = ["Brand Strategy", "Visual Identity", "Logo Design", "Voice & Tone", "Color Systems", "Creative Direction", "Typography", "Brand Story"];
  return (
    <div style={{
      overflow: "hidden", width: "100vw", marginLeft: "-48px",
      borderTop: "1.5px solid rgba(0,0,0,0.06)",
      borderBottom: "1.5px solid rgba(0,0,0,0.06)",
      padding: "14px 0",
    }}>
      <div style={{ display: "flex", animation: "marquee 30s linear infinite", width: "max-content" }}>
        {[...items, ...items, ...items, ...items].map((item, i) => (
          <span key={i} style={{
            display: "inline-flex", alignItems: "center", gap: 20,
            paddingRight: 20, whiteSpace: "nowrap",
            fontFamily: "'Bebas Neue', sans-serif", fontSize: 15,
            color: "rgba(0,0,0,0.18)", letterSpacing: "0.15em",
            textTransform: "uppercase",
          }}>
            {item}
            <span style={{ color: RED, fontSize: 8 }}>◆</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── COUNTER ANIMATION ───
function AnimatedCounter({ target, duration = 2000, delay = 0, suffix = "" }) {
  const [value, setValue] = useState(0);
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setStarted(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  useEffect(() => {
    if (!started) return;
    const start = performance.now();
    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 4);
      setValue(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [started, target, duration]);
  return <span>{value}{suffix}</span>;
}

// ─── PARALLAX CONTAINER ───
function ParallaxField({ children }) {
  const [mouse, setMouse] = useState({ x: 0.5, y: 0.5 });
  return (
    <div
      onMouseMove={e => setMouse({ x: e.clientX / window.innerWidth, y: e.clientY / window.innerHeight })}
      style={{ position: "relative", minHeight: "100vh" }}
    >
      {typeof children === "function" ? children(mouse) : children}
    </div>
  );
}


// ═══════════════ HERO STAGE ═══════════════
function HeroStage({ onStart }) {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { setTimeout(() => setLoaded(true), 200); }, []);

  return (
    <ParallaxField>
      {(mouse) => (
        <div style={{
          display: "flex", flexDirection: "column",
          minHeight: "100vh", padding: "0 48px 60px 56px",
          justifyContent: "center", position: "relative",
        }}>
          {/* Animated grid background */}
          <div style={{
            position: "fixed", inset: 0, zIndex: 0, overflow: "hidden",
          }}>
            {/* Grid that shifts with mouse */}
            <div style={{
              position: "absolute", inset: -20,
              backgroundImage: `linear-gradient(rgba(0,0,0,0.028) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.028) 1px, transparent 1px)`,
              backgroundSize: "80px 80px",
              transform: `translate(${(mouse.x - 0.5) * 8}px, ${(mouse.y - 0.5) * 8}px)`,
              transition: "transform 0.3s ease-out",
            }} />

            {/* Decorative large number in bg */}
            <div style={{
              position: "absolute", bottom: -60, right: -20,
              fontSize: 400, fontWeight: 900, color: "rgba(0,0,0,0.018)",
              fontFamily: "'Bebas Neue', sans-serif", lineHeight: 0.85,
              transform: `translate(${(mouse.x - 0.5) * -20}px, ${(mouse.y - 0.5) * -15}px)`,
              transition: "transform 0.4s ease-out",
              userSelect: "none",
            }}>60</div>

            {/* Geometric shapes */}
            <div style={{
              position: "absolute", top: "12%", right: "12%",
              width: 120, height: 120,
              border: "1.5px solid rgba(0,0,0,0.04)",
              transform: `rotate(45deg) translate(${(mouse.x - 0.5) * -25}px, ${(mouse.y - 0.5) * -20}px)`,
              transition: "transform 0.5s ease-out",
            }} />
            <div style={{
              position: "absolute", top: "18%", right: "16%",
              width: 80, height: 80, borderRadius: "50%",
              border: "1.5px solid rgba(230,57,70,0.08)",
              transform: `translate(${(mouse.x - 0.5) * -15}px, ${(mouse.y - 0.5) * -12}px)`,
              transition: "transform 0.6s ease-out",
            }} />
            <div style={{
              position: "absolute", bottom: "25%", left: "8%",
              width: 60, height: 60,
              border: "1.5px solid rgba(0,0,0,0.03)",
              borderRadius: "50%",
              transform: `translate(${(mouse.x - 0.5) * 15}px, ${(mouse.y - 0.5) * 12}px)`,
              transition: "transform 0.5s ease-out",
            }} />
          </div>

          {/* Red accent stripe — draws in */}
          <div style={{
            position: "fixed", top: 0, left: 0, width: 5,
            height: loaded ? "100%" : "0%",
            background: RED, zIndex: 10,
            transition: "height 1.2s cubic-bezier(0.16,1,0.3,1)",
            transitionDelay: "300ms",
          }} />

          {/* Top bar */}
          <div style={{
            position: "absolute", top: 40, left: 56, right: 48,
            display: "flex", justifyContent: "space-between", alignItems: "flex-start",
            zIndex: 5,
          }}>
            <Reveal delay={800} from="left">
              <div>
                <div style={{
                  fontSize: 11, fontWeight: 700, letterSpacing: "0.2em",
                  color: RED, fontFamily: "'Syne', sans-serif",
                  textTransform: "uppercase",
                }}>
                  <ScrambleText text="BRANDSTORM®" />
                </div>
                <div style={{
                  fontSize: 10, color: "rgba(0,0,0,0.2)", marginTop: 4,
                  fontFamily: "'Syne', monospace", letterSpacing: "0.1em",
                }}>AI CREATIVE DIRECTOR</div>
              </div>
            </Reveal>
            <Reveal delay={1000} from="right">
              <RotatingBadge />
            </Reveal>
          </div>

          {/* Main content */}
          <div style={{ maxWidth: 1000, position: "relative", zIndex: 3 }}>
            {/* Headline — kinetic letter reveal */}
            <h1 style={{ lineHeight: 0.88, marginBottom: 36 }}>
              <div style={{
                fontSize: "min(14vw, 140px)", fontWeight: 400,
                fontFamily: "'Bebas Neue', sans-serif",
                letterSpacing: "0.02em", textTransform: "uppercase",
                overflow: "hidden",
              }}>
                <KineticWord text="From" baseDelay={400} stagger={50} from="bottom" />
              </div>
              <div style={{
                fontSize: "min(14vw, 140px)", fontWeight: 400,
                fontFamily: "'Bebas Neue', sans-serif",
                letterSpacing: "0.02em", textTransform: "uppercase",
                WebkitTextStroke: `2px ${INK}`,
                WebkitTextFillColor: "transparent",
                overflow: "hidden",
              }}>
                <KineticWord text="Product" baseDelay={600} stagger={45} from="bottom"
                  style={{ WebkitTextStroke: `2px ${INK}`, WebkitTextFillColor: "transparent" }} />
              </div>
              <div style={{
                fontSize: "min(14vw, 140px)", fontWeight: 400,
                fontFamily: "'Bebas Neue', sans-serif",
                letterSpacing: "0.02em", textTransform: "uppercase",
                overflow: "hidden",
              }}>
                <KineticWord text="to Brand" baseDelay={850} stagger={45} from="bottom" color={RED} />
              </div>
            </h1>

            {/* Sub-content row */}
            <div style={{
              display: "flex", gap: 48, alignItems: "flex-end",
              marginBottom: 24, flexWrap: "wrap",
            }}>
              <Reveal delay={1400} from="bottom">
                <p style={{
                  fontSize: 15, color: "rgba(0,0,0,0.35)",
                  maxWidth: 320, lineHeight: 1.75,
                  fontFamily: "'Syne', sans-serif",
                  borderLeft: `3px solid ${RED}`,
                  paddingLeft: 20,
                }}>
                  Upload a photo. Converse with your AI creative director.
                  Receive a complete brand identity in seconds.
                </p>
              </Reveal>

              <Reveal delay={1600} from="bottom">
                <div style={{ display: "flex", gap: 32, fontFamily: "'Syne', sans-serif" }}>
                  {[
                    { label: "STRATEGY", num: 1 },
                    { label: "IDENTITY", num: 2 },
                    { label: "VOICE", num: 3 },
                  ].map((item) => (
                    <div key={item.label} style={{ textAlign: "center", cursor: "default" }}
                      onMouseEnter={e => e.currentTarget.querySelector('.num').style.color = RED}
                      onMouseLeave={e => e.currentTarget.querySelector('.num').style.color = INK}
                    >
                      <div className="num" style={{
                        fontSize: 42, fontWeight: 400, color: INK,
                        fontFamily: "'Bebas Neue', sans-serif",
                        transition: "color 0.3s", letterSpacing: "0.02em",
                      }}>
                        <AnimatedCounter target={item.num} duration={800} delay={1800 + item.num * 200} suffix="" />
                        <span style={{ fontSize: 42 }}>{"0".concat(item.num).slice(-2).charAt(0) === "0" ? "" : ""}</span>
                        0{item.num}
                      </div>
                      <div style={{
                        fontSize: 9, color: "rgba(0,0,0,0.25)",
                        letterSpacing: "0.15em", marginTop: 2,
                      }}>
                        <ScrambleText text={item.label} />
                      </div>
                    </div>
                  ))}
                </div>
              </Reveal>
            </div>

            {/* Marquee */}
            <Reveal delay={1800} from="bottom">
              <Marquee />
            </Reveal>

            {/* CTA */}
            <Reveal delay={2100} from="bottom" style={{ marginTop: 40 }}>
              <MagneticButton onClick={onStart}>
                Create Your Brand
              </MagneticButton>
            </Reveal>
          </div>

          {/* Bottom info */}
          <Reveal delay={2400} from="bottom" style={{
            position: "absolute", bottom: 32, left: 56,
          }}>
            <div style={{
              fontSize: 10, color: "rgba(0,0,0,0.15)",
              fontFamily: "'Syne', monospace", letterSpacing: "0.12em",
              display: "flex", gap: 24,
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


// ═══════════════ UPLOAD STAGE ═══════════════
function UploadStage({ onBack, onGenerate }) {
  const [hasImage, setHasImage] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [entering, setEntering] = useState(false);
  const [pulseCount, setPulseCount] = useState(0);
  const fileRef = useRef(null);

  useEffect(() => { setTimeout(() => setEntering(true), 100); }, []);
  useEffect(() => {
    if (!isDragging) return;
    const i = setInterval(() => setPulseCount(p => p + 1), 600);
    return () => clearInterval(i);
  }, [isDragging]);

  return (
    <ParallaxField>
      {(mouse) => (
        <div style={{
          display: "flex", minHeight: "100vh", padding: "0 48px 60px 56px",
          alignItems: "center", justifyContent: "center",
          position: "relative",
          opacity: entering ? 1 : 0,
          transition: "opacity 0.8s ease",
        }}>
          {/* Background grid */}
          <div style={{
            position: "fixed", inset: 0, zIndex: 0,
            backgroundImage: `linear-gradient(rgba(0,0,0,0.028) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.028) 1px, transparent 1px)`,
            backgroundSize: "80px 80px",
            transform: `translate(${(mouse.x - 0.5) * 5}px, ${(mouse.y - 0.5) * 5}px)`,
            transition: "transform 0.3s ease-out",
          }} />

          {/* Red stripe */}
          <div style={{
            position: "fixed", top: 0, left: 0, bottom: 0, width: 5,
            background: RED, zIndex: 10,
          }} />

          {/* Back button */}
          <Reveal delay={300} from="left">
            <button onClick={onBack} style={{
              position: "absolute", top: 40, left: 56, zIndex: 5,
              background: "none", border: `2px solid rgba(0,0,0,0.08)`,
              padding: "10px 24px", cursor: "pointer",
              fontSize: 11, fontWeight: 700, color: "rgba(0,0,0,0.3)",
              fontFamily: "'Syne', sans-serif", letterSpacing: "0.12em",
              textTransform: "uppercase",
              transition: "all 0.3s ease",
            }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = RED; e.currentTarget.style.color = RED; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(0,0,0,0.08)"; e.currentTarget.style.color = "rgba(0,0,0,0.3)"; }}
            >← Back</button>
          </Reveal>

          <div style={{ maxWidth: 580, width: "100%", position: "relative", zIndex: 3 }}>
            <Reveal delay={200} from="left">
              <div style={{
                fontSize: 10, fontWeight: 700, color: RED, letterSpacing: "0.25em",
                fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
                marginBottom: 16, display: "flex", alignItems: "center", gap: 12,
              }}>
                <div style={{
                  width: 32, height: 1.5, background: RED,
                }} />
                Step 01 — The Brief
              </div>
            </Reveal>

            <div style={{ overflow: "hidden", marginBottom: 48 }}>
              <h2 style={{
                fontSize: "min(10vw, 72px)", fontWeight: 400, color: INK,
                fontFamily: "'Bebas Neue', sans-serif",
                letterSpacing: "0.02em", textTransform: "uppercase",
                lineHeight: 0.92,
              }}>
                <KineticWord text="Show Us" baseDelay={400} stagger={50} from="bottom" />
                <br/>
                <KineticWord text="Your Product" baseDelay={650} stagger={40} from="bottom" />
              </h2>
            </div>

            {/* Upload zone */}
            <Reveal delay={900} from="bottom">
              <div
                onClick={() => !hasImage && fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={e => { e.preventDefault(); setIsDragging(false); setHasImage(true); }}
                style={{
                  position: "relative", minHeight: hasImage ? "auto" : 320,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer",
                  border: `2px solid ${isDragging ? RED : "rgba(0,0,0,0.07)"}`,
                  background: isDragging ? "rgba(230,57,70,0.02)" : "rgba(255,255,255,0.3)",
                  transition: "all 0.4s cubic-bezier(0.16,1,0.3,1)",
                  overflow: "hidden",
                }}
              >
                <input ref={fileRef} type="file" accept="image/*" hidden onChange={() => setHasImage(true)} />

                {/* Corner brackets */}
                {[
                  { top: 12, left: 12, bT: true, bL: true },
                  { top: 12, right: 12, bT: true, bR: true },
                  { bottom: 12, left: 12, bB: true, bL: true },
                  { bottom: 12, right: 12, bB: true, bR: true },
                ].map((p, i) => {
                  const { bT, bR, bB, bL, ...pos } = p;
                  const c = isDragging ? RED : "rgba(0,0,0,0.1)";
                  return (
                    <div key={i} style={{
                      position: "absolute", ...pos, width: 24, height: 24,
                      borderTop: bT ? `2px solid ${c}` : "none",
                      borderRight: bR ? `2px solid ${c}` : "none",
                      borderBottom: bB ? `2px solid ${c}` : "none",
                      borderLeft: bL ? `2px solid ${c}` : "none",
                      transition: "border-color 0.3s",
                    }} />
                  );
                })}

                {/* Drag pulse rings */}
                {isDragging && (
                  <div style={{
                    position: "absolute", inset: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    pointerEvents: "none",
                  }}>
                    {[0, 1, 2].map(i => (
                      <div key={`${pulseCount}-${i}`} style={{
                        position: "absolute",
                        width: 80 + i * 40, height: 80 + i * 40,
                        borderRadius: "50%",
                        border: `1.5px solid ${RED}`,
                        opacity: 0,
                        animation: `pulse 1.8s ${i * 0.3}s cubic-bezier(0.16,1,0.3,1) infinite`,
                      }} />
                    ))}
                  </div>
                )}

                {!hasImage ? (
                  <div style={{ textAlign: "center", padding: "52px 32px" }}>
                    <div style={{
                      fontSize: 80, fontWeight: 400, color: isDragging ? RED : "rgba(0,0,0,0.04)",
                      fontFamily: "'Bebas Neue', sans-serif",
                      transition: "all 0.4s", lineHeight: 1,
                      transform: isDragging ? "scale(1.1)" : "scale(1)",
                      marginBottom: 12,
                    }}>↑</div>
                    <div style={{
                      fontSize: 14, fontWeight: 700, color: isDragging ? RED : INK,
                      fontFamily: "'Syne', sans-serif",
                      textTransform: "uppercase", letterSpacing: "0.12em",
                      marginBottom: 8, transition: "color 0.3s",
                    }}>{isDragging ? "Release" : "Drop Product Photo"}</div>
                    <div style={{
                      fontSize: 12, color: "rgba(0,0,0,0.22)",
                      fontFamily: "'Syne', sans-serif",
                    }}>or click to browse · PNG, JPG</div>
                  </div>
                ) : (
                  <div style={{ width: "100%", position: "relative" }}>
                    <div style={{
                      width: "100%", aspectRatio: "3/2",
                      background: `linear-gradient(135deg, ${CREAM}, #e8e0d8)`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      <div style={{
                        width: 56, height: 112, borderRadius: "28px 28px 6px 6px",
                        background: "linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.15))",
                        border: "1px solid rgba(0,0,0,0.06)",
                        boxShadow: "0 20px 60px rgba(0,0,0,0.06)",
                      }} />
                    </div>
                    <div style={{
                      position: "absolute", top: 14, left: 14,
                      padding: "5px 12px", background: RED, color: "white",
                      fontSize: 9, fontWeight: 700, letterSpacing: "0.12em",
                      fontFamily: "'Syne', sans-serif",
                    }}>UPLOADED</div>
                  </div>
                )}
              </div>
            </Reveal>

            {hasImage && (
              <>
                <Reveal delay={100} from="bottom">
                  <div style={{
                    marginTop: 14, padding: "16px 22px",
                    border: "2px solid rgba(0,0,0,0.05)",
                    background: "rgba(255,255,255,0.4)",
                  }}>
                    <input type="text"
                      placeholder="Describe your product, audience, or desired vibe..."
                      style={{
                        width: "100%", border: "none", background: "transparent",
                        outline: "none", fontSize: 14, color: INK,
                        fontFamily: "'Syne', sans-serif",
                      }}
                    />
                  </div>
                </Reveal>
                <Reveal delay={250} from="bottom" style={{ marginTop: 36 }}>
                  <MagneticButton onClick={onGenerate}>
                    Start Creative Session
                  </MagneticButton>
                </Reveal>
              </>
            )}
          </div>
        </div>
      )}
    </ParallaxField>
  );
}


// ═══════════════ DONE STAGE ═══════════════
function DoneStage() {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min((now - start) / 3000, 1);
      setProgress(p);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, []);

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "100vh", position: "relative",
    }}>
      <div style={{
        position: "fixed", inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(rgba(0,0,0,0.028) 1px, transparent 1px),linear-gradient(90deg, rgba(0,0,0,0.028) 1px, transparent 1px)`,
        backgroundSize: "80px 80px",
      }} />
      <div style={{ position: "fixed", top: 0, left: 0, bottom: 0, width: 5, background: RED, zIndex: 10 }} />

      <div style={{
        position: "relative", zIndex: 3,
        padding: "60px 80px", textAlign: "center",
        border: "2px solid rgba(0,0,0,0.06)",
        background: "rgba(255,255,255,0.4)",
        animation: "doneReveal 0.8s cubic-bezier(0.16,1,0.3,1) both",
      }}>
        {/* Progress ring */}
        <div style={{ margin: "0 auto 24px", width: 80, height: 80, position: "relative" }}>
          <svg width="80" height="80" viewBox="0 0 80 80" style={{ transform: "rotate(-90deg)" }}>
            <circle cx="40" cy="40" r="34" fill="none" stroke="rgba(0,0,0,0.04)" strokeWidth="3" />
            <circle cx="40" cy="40" r="34" fill="none" stroke={RED} strokeWidth="3"
              strokeDasharray={`${progress * 213.6} 213.6`}
              strokeLinecap="round"
              style={{ transition: "stroke-dasharray 0.1s ease" }}
            />
          </svg>
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 700, fontFamily: "'Bebas Neue', sans-serif",
            color: progress >= 1 ? RED : INK, letterSpacing: "0.04em",
            transition: "color 0.3s",
          }}>{Math.round(progress * 100)}%</div>
        </div>

        <div style={{ overflow: "hidden" }}>
          <h3 style={{
            fontSize: 36, fontWeight: 400, color: INK,
            fontFamily: "'Bebas Neue', sans-serif",
            letterSpacing: "0.04em", textTransform: "uppercase",
            marginBottom: 8,
          }}>
            <KineticWord text="Session Starting" baseDelay={300} stagger={40} from="bottom" />
          </h3>
        </div>
        <div style={{
          fontSize: 12, color: "rgba(0,0,0,0.25)",
          fontFamily: "'Syne', sans-serif", letterSpacing: "0.08em",
        }}>→ GEMINI LIVE AGENT TAKES OVER</div>
      </div>
    </div>
  );
}


// ═══════════════ APP ═══════════════
export default function App() {
  const [stage, setStage] = useState("hero");
  const [transitioning, setTransitioning] = useState(false);

  const switchStage = (next) => {
    setTransitioning(true);
    setTimeout(() => { setStage(next); setTransitioning(false); }, 450);
  };

  return (
    <div style={{
      fontFamily: "'Syne', sans-serif",
      minHeight: "100vh", position: "relative", overflow: "hidden",
      background: CREAM,
    }}>
      <div style={{
        opacity: transitioning ? 0 : 1,
        transform: transitioning ? "scale(0.97)" : "scale(1)",
        transition: "all 0.45s cubic-bezier(0.16,1,0.3,1)",
      }}>
        {stage === "hero" && <HeroStage onStart={() => switchStage("upload")} />}
        {stage === "upload" && (
          <UploadStage onBack={() => switchStage("hero")} onGenerate={() => switchStage("done")} />
        )}
        {stage === "done" && <DoneStage />}
      </div>

      <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Syne:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
      <style>{`
        * { margin: 0; padding: 0; box-sizing: border-box; }
        input::placeholder { color: rgba(0,0,0,0.22) !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes pulse {
          0% { transform: scale(0.5); opacity: 0.6; }
          100% { transform: scale(2.5); opacity: 0; }
        }
        @keyframes doneReveal {
          from { opacity: 0; transform: translateY(30px) scale(0.95); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
