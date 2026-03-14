import { useState, useEffect, useRef, useCallback } from 'react';
import { raw, fonts, easeCurve } from '../styles/tokens';
import KineticWord from './KineticWord';

/**
 * LaunchSequence — the "wow moment" overlay.
 *
 * Flow:
 *  1. (0s)  Screen dims to dark. Product image lifts to center. Geometric shape pulses. "CONNECTING..."
 *  2. (on firstAgentText) Parse dramatic opener (before first period/newline) → BIG kinetic display.
 *     Red DrawLine animates below.
 *  3. (2s later) Agent intro (second sentence) fades in below — Syne italic, muted.
 *  4. (2s later) Everything fades out, onComplete fires → StudioScreen takes over.
 *
 * Props:
 *  - imagePreview: data URL of uploaded product image
 *  - firstAgentText: first agent_text string (may arrive late or never)
 *  - onComplete: callback to transition to StudioScreen
 */

const EASE = `cubic-bezier(${easeCurve.join(',')})`;

/**
 * Parse agent text into { opener, intro, rest }.
 *
 * Expected format from the agent:
 *   "Golden. Sculpted. Iconic.\nI'm Charon, your creative director. Let's build something extraordinary.\nI see gold hoops on warm wood..."
 *
 * The opener is the dramatic 3-word reaction (everything up to the first
 * sentence that does NOT look like a single-word-period pattern).
 * The intro is the next sentence (agent self-introduction).
 * The rest is everything after.
 *
 * Graceful degradation: if format is unexpected, first sentence = opener.
 */
function parseAgentText(text) {
  if (!text) return { opener: '', intro: '', rest: '' };

  // Split on newlines first (agent should separate opener/intro/analysis with newlines)
  const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean);

  if (lines.length >= 3) {
    return { opener: lines[0], intro: lines[1], rest: lines.slice(2).join(' ') };
  }
  if (lines.length === 2) {
    return { opener: lines[0], intro: lines[1], rest: '' };
  }

  // No newlines — try splitting on sentence boundaries
  // Handle both "Word. Word." and "Word.Word" (no space after period before capital)
  // e.g. "Golden. Sculpted. Iconic. I'm Charon..." or "Golden.Sculpted.I'm Charon..."
  const sentences = text.split(/(?<=\.)(?:\s+|(?=[A-Z]))/).map(s => s.trim()).filter(Boolean);

  if (sentences.length === 0) return { opener: text, intro: '', rest: '' };

  // Find where the opener ends — opener words are short (< 15 chars) and period-terminated
  let openerEnd = 0;
  for (let i = 0; i < sentences.length; i++) {
    const s = sentences[i];
    // If this looks like a single dramatic word (short, ends with period, no spaces)
    if (s.length < 15 && !s.includes(' ')) {
      openerEnd = i + 1;
    } else {
      break;
    }
  }

  // If we found dramatic words, join them as opener
  if (openerEnd > 0) {
    const opener = sentences.slice(0, openerEnd).join(' ');
    const remaining = sentences.slice(openerEnd);
    if (remaining.length === 0) return { opener, intro: '', rest: '' };
    if (remaining.length === 1) return { opener, intro: remaining[0], rest: '' };

    // Check if the sentence immediately after the intro sentence is a greeting
    // continuation (e.g. "Let's build something extraordinary." after
    // "I'm Charon, your creative director."). If so, include it in the intro
    // block so it doesn't leak into the chat as fake "analysis" content.
    const afterIntro = remaining[1];
    const isGreetingContinuation =
      /^let'?s\b|^together\b|^shall we\b/i.test(afterIntro) && afterIntro.length < 80;

    if (isGreetingContinuation) {
      const intro = remaining[0] + ' ' + remaining[1];
      return { opener, intro, rest: remaining.slice(2).join(' ') };
    }

    return { opener, intro: remaining[0], rest: remaining.slice(1).join(' ') };
  }

  // Fallback: first sentence is opener
  if (sentences.length === 1) return { opener: sentences[0], intro: '', rest: '' };
  if (sentences.length === 2) return { opener: sentences[0], intro: sentences[1], rest: '' };
  return { opener: sentences[0], intro: sentences[1], rest: sentences.slice(2).join(' ') };
}

// ─── Pulsing Geometric Shape ───
function GeoShape({ pulsing, exploded }) {
  return (
    <div style={{ position: 'relative', width: 80, height: 80, margin: '0 auto' }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          position: 'absolute',
          inset: i * 8,
          border: `1.5px solid ${exploded ? raw.red : 'rgba(255,255,255,0.12)'}`,
          opacity: exploded ? 0 : (pulsing ? 0.6 : 0.3),
          transform: exploded
            ? `scale(${1.4 - i * 0.1})`
            : pulsing
              ? `scale(${1 + i * 0.05})`
              : 'scale(1)',
          transition: exploded
            ? `all 0.4s ${EASE}`
            : 'all 0.6s ease',
          animation: pulsing && !exploded
            ? `launchRingPulse 1.2s ${i * 0.15}s ease-in-out infinite`
            : 'none',
        }} />
      ))}
    </div>
  );
}

// ─── Red Draw Line ───
function RedDrawLine({ active, delay = 0 }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setDrawn(true), delay);
    return () => clearTimeout(t);
  }, [active, delay]);

  return (
    <div style={{
      height: 2, background: raw.red, margin: '0 auto',
      width: drawn ? 180 : 0,
      transition: `width 0.6s ${EASE}`,
    }} />
  );
}

// ─── Intro Text (agent's self-introduction) ───
function IntroText({ text, visible }) {
  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(12px)',
      transition: `all 0.7s ${EASE}`,
      textAlign: 'center',
    }}>
      <p style={{
        fontSize: 16, color: 'rgba(255,255,255,0.45)',
        fontFamily: fonts.body, fontStyle: 'italic',
        maxWidth: 400, lineHeight: 1.6, margin: '0 auto 12px',
      }}>
        {text}
      </p>
      <div style={{
        fontSize: 9, color: 'rgba(255,255,255,0.15)',
        fontFamily: fonts.body, letterSpacing: '0.2em',
        textTransform: 'uppercase', marginTop: 16,
      }}>
        BRANDSTORM® · CREATIVE STORYTELLER
      </div>
    </div>
  );
}

// ═══════════ LAUNCH SEQUENCE ═══════════
export default function LaunchSequence({ imagePreview, firstAgentText, openingData, onComplete }) {
  // Phases: dimming → connecting → words → intro → transition
  const [phase, setPhase] = useState('dimming');
  const [dimLevel, setDimLevel] = useState(0);
  const completeFired = useRef(false);
  const introTimerRef = useRef(null);
  const transTimerRef = useRef(null);
  const doneTimerRef = useRef(null);
  const wordsTriggered = useRef(false);

  // Parse the latest accumulated text — opener is locked at words phase,
  // intro updates as more text streams in
  const [lockedOpener, setLockedOpener] = useState('');
  const [lockedIntro, setLockedIntro] = useState('');
  const parsed = parseAgentText(firstAgentText);

  const fireComplete = useCallback(() => {
    if (completeFired.current) return;
    completeFired.current = true;
    onComplete();
  }, [onComplete]);

  // Phase 1: dimming → connecting (automatic, time-based)
  useEffect(() => {
    const t = setTimeout(() => {
      setDimLevel(1);
      setPhase('connecting');
    }, 300);
    return () => clearTimeout(t);
  }, []);

  // Phase 2: When openingData or firstAgentText arrives, move to 'words' phase
  useEffect(() => {
    if (wordsTriggered.current) return;

    // Priority 1: structured openingData from text-model call
    if (openingData?.words?.length >= 2) {
      wordsTriggered.current = true;
      const openerStr = openingData.words.map(w => w + '.').join(' ');
      setLockedOpener(openerStr);
      setLockedIntro(openingData.intro || "I'm Charon, your creative director. Let's build something extraordinary.");
      setPhase('words');
    }
    // Priority 2: parsed from transcription (fallback)
    else if (firstAgentText && parsed.opener && parsed.opener.includes('.')) {
      wordsTriggered.current = true;
      setLockedOpener(parsed.opener);
      setLockedIntro(parsed.intro || "I'm Charon, your creative director. Let's build something extraordinary.");
      setPhase('words');
    }
    else {
      return; // not ready yet
    }

    // 1.5s after words → show intro (by then more text may have arrived)
    introTimerRef.current = setTimeout(() => {
      setPhase('intro');
    }, 1500);

    // 3s after intro → begin transition (gives 4.5s total for intro to be visible)
    transTimerRef.current = setTimeout(() => {
      setPhase('transition');
    }, 4500);

    // Transition out, then fire complete
    doneTimerRef.current = setTimeout(() => {
      fireComplete();
    }, 5200);

    return () => {
      // Only clear timers if words phase hasn't triggered yet.
      // Once wordsTriggered = true the timers must run to completion.
      if (!wordsTriggered.current) {
        clearTimeout(introTimerRef.current);
        clearTimeout(transTimerRef.current);
        clearTimeout(doneTimerRef.current);
      }
    };
  }, [openingData, firstAgentText, parsed.opener, fireComplete]);

  // Fallback: if nothing triggered words after 7s, use whatever text we have or skip
  useEffect(() => {
    const t = setTimeout(() => {
      if (!wordsTriggered.current) {
        wordsTriggered.current = true;
        // Use accumulated transcription if available, otherwise default
        const fallbackOpener = parsed.opener || firstAgentText || '';
        setLockedOpener(fallbackOpener);
        setLockedIntro(parsed.intro || "I'm Charon, your creative director. Let's build something extraordinary.");
        setPhase(fallbackOpener ? 'words' : 'transition');
        if (fallbackOpener) {
          introTimerRef.current = setTimeout(() => setPhase('intro'), 1500);
          transTimerRef.current = setTimeout(() => setPhase('transition'), 4500);
          doneTimerRef.current = setTimeout(() => fireComplete(), 5200);
        } else {
          doneTimerRef.current = setTimeout(() => fireComplete(), 600);
        }
      }
    }, 7000);
    return () => clearTimeout(t);
  }, [fireComplete, parsed.opener, parsed.intro, firstAgentText]);

  // Hard fallback: if still not complete after 12s, transition anyway
  useEffect(() => {
    const t = setTimeout(() => {
      if (!completeFired.current) {
        setPhase('transition');
        setTimeout(() => fireComplete(), 600);
      }
    }, 12000);
    return () => clearTimeout(t);
  }, [fireComplete]);

  const isConnecting = phase === 'dimming' || phase === 'connecting';
  const showWords = phase === 'words' || phase === 'intro' || phase === 'transition';
  const showIntro = phase === 'intro' || phase === 'transition';
  const isTransitioning = phase === 'transition';

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Dark overlay — dims the entire screen */}
      <div style={{
        position: 'absolute', inset: 0,
        background: raw.ink,
        opacity: isTransitioning ? 0 : dimLevel * 0.85,
        transition: `opacity 0.8s ${EASE}`,
        zIndex: 0,
      }} />

      {/* Subtle grid visible through the darkness */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 1,
        backgroundImage: `linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)`,
        backgroundSize: '52px 52px',
        opacity: dimLevel * 0.5,
        transition: 'opacity 0.8s ease',
      }} />

      {/* Red stripe — left edge */}
      <div style={{
        position: 'absolute', top: 0, left: 0, bottom: 0, width: 5,
        background: raw.red, zIndex: 10,
        opacity: dimLevel,
        transition: 'opacity 0.5s ease',
      }} />

      {/* Content — fixed layout, no jumping */}
      <div style={{
        position: 'relative', zIndex: 5,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center',
        opacity: isTransitioning ? 0 : 1,
        transform: isTransitioning ? 'translateY(-30px) scale(0.95)' : 'translateY(0) scale(1)',
        transition: `all 0.6s ${EASE}`,
      }}>
        {/* Product image — always present, never moves */}
        <div style={{
          width: 160, overflow: 'hidden',
          border: '2px solid rgba(255,255,255,0.1)',
          opacity: phase === 'dimming' ? 0 : 1,
          transform: phase === 'dimming' ? 'translateY(20px) scale(0.9)' : 'translateY(0) scale(1)',
          transition: `all 0.8s ${EASE}`,
          boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
          position: 'relative',
        }}>
          {imagePreview && (
            <img src={imagePreview} alt="Product" style={{
              width: '100%', display: 'block',
            }} />
          )}
          <div style={{
            position: 'absolute', top: 8, left: 8,
            padding: '3px 8px', background: raw.red, color: raw.white,
            fontSize: 8, fontWeight: 700, letterSpacing: '0.1em',
            fontFamily: fonts.body, textTransform: 'uppercase',
          }}>UPLOADED</div>
        </div>

        {/* Below-image zone — fixed height, elements fade in/out in place */}
        <div style={{
          position: 'relative',
          width: 500, height: 320,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'flex-start',
          paddingTop: 28,
        }}>
          {/* Connecting state — absolutely positioned so it doesn't affect layout */}
          <div style={{
            position: 'absolute', top: 28, left: 0, right: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            opacity: isConnecting ? 1 : 0,
            transition: `opacity 0.5s ${EASE}`,
            pointerEvents: isConnecting ? 'auto' : 'none',
          }}>
            <GeoShape pulsing={phase === 'connecting'} exploded={false} />
            <div style={{
              marginTop: 24,
              fontSize: 12, fontWeight: 700, color: 'rgba(255,255,255,0.3)',
              letterSpacing: '0.3em', textTransform: 'uppercase',
              fontFamily: fonts.body,
            }}>
              CONNECTING...
            </div>
            <div style={{
              width: 120, height: 2, marginTop: 16,
              background: 'rgba(255,255,255,0.06)',
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%', background: raw.red,
                animation: 'launchLoadingBar 1.5s ease-in-out infinite',
              }} />
            </div>
          </div>

          {/* Words + line + intro — absolutely positioned, fades in when ready */}
          <div style={{
            position: 'absolute', top: 20, left: 0, right: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            opacity: showWords ? 1 : 0,
            transition: `opacity 0.5s ${EASE}`,
            pointerEvents: showWords ? 'auto' : 'none',
          }}>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <DramaticOpener text={lockedOpener || parsed.opener} />
            </div>

            <div style={{ marginBottom: 28 }}>
              <RedDrawLine active={showWords} delay={900} />
            </div>

            <IntroText
              text={lockedIntro || parsed.intro || "I'm Charon, your creative director.\nLet's build something extraordinary."}
              visible={showIntro}
            />
          </div>
        </div>
      </div>

      <style>{`
        @keyframes launchRingPulse {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.08); opacity: 0.6; }
        }
        @keyframes launchLoadingBar {
          0% { width: 0%; margin-left: 0; }
          50% { width: 100%; margin-left: 0; }
          100% { width: 0%; margin-left: 100%; }
        }
      `}</style>
    </div>
  );
}

// ─── Dramatic Opener: split on periods, each word appears with stagger ───
function DramaticOpener({ text }) {
  if (!text) return null;

  // Split "Golden. Sculpted. Iconic." into individual period-delimited words
  const segments = text.split(/\.\s*/).map(s => s.trim()).filter(Boolean);

  // If we got period-separated words (the ideal 3-word format), show each big
  if (segments.length >= 2) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
        {segments.map((word, i) => (
          <WordReveal key={i} text={word + '.'} delay={i * 350} />
        ))}
      </div>
    );
  }

  // Fallback: show whatever the first sentence is as one big kinetic line
  return (
    <div style={{ maxWidth: 500 }}>
      <div style={{
        fontFamily: fonts.display, fontSize: 48,
        textTransform: 'uppercase', letterSpacing: '0.06em',
        lineHeight: 1, color: raw.white,
        textAlign: 'center',
      }}>
        <KineticWord
          text={text.slice(0, 60)}
          baseDelay={0} stagger={30} from="bottom"
          color={raw.white}
        />
      </div>
    </div>
  );
}

// ─── Single word reveal with slide-up animation ───
function WordReveal({ text, delay }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div style={{ overflow: 'hidden', lineHeight: 1 }}>
      <div style={{
        fontSize: 52,
        fontWeight: 400,
        fontFamily: fonts.display,
        color: raw.white,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        transform: visible ? 'translateY(0)' : 'translateY(110%)',
        opacity: visible ? 1 : 0,
        transition: `all 0.8s ${EASE}`,
      }}>
        {text}
      </div>
    </div>
  );
}

// Export parser so App.jsx can use it to split text for StudioScreen
export { parseAgentText };
