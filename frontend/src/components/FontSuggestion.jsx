import { useState, useEffect, useRef } from 'react';
import { raw, fonts } from '../styles/tokens';

function loadGoogleFont(family) {
  if (!family) return;
  const id = `gfont-${family.replace(/\s/g, '-')}`;
  if (document.getElementById(id)) return;
  const link = document.createElement('link');
  link.id = id;
  link.href = `https://fonts.googleapis.com/css2?family=${family.replace(/ /g, '+')}&display=swap`;
  link.rel = 'stylesheet';
  document.head.appendChild(link);
}

function useFontLoaded(family) {
  const [loaded, setLoaded] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!family) return;
    loadGoogleFont(family);
    const check = () => {
      if (document.fonts.check(`16px '${family}'`)) {
        setLoaded(true);
        clearInterval(intervalRef.current);
      }
    };
    check();
    intervalRef.current = setInterval(check, 150);
    const t = setTimeout(() => {
      setLoaded(true);
      clearInterval(intervalRef.current);
    }, 3000);
    return () => {
      clearInterval(intervalRef.current);
      clearTimeout(t);
    };
  }, [family]);

  return loaded;
}

export default function FontSuggestion({ heading, body, rationale, brandName, tagline }) {
  const headingLoaded = useFontLoaded(heading?.family);
  const bodyLoaded = useFontLoaded(body?.family);

  const sampleName = brandName || 'Your Brand';
  const sampleTagline = tagline || 'Where ideas become reality';

  if (!heading?.family && !body?.family) return null;

  return (
    <div style={{
      padding: '16px 18px',
      border: `2px solid ${raw.line}`,
      background: 'rgba(255,255,255,0.4)',
    }}>
      {/* Label */}
      <div style={{
        fontSize: 8, fontWeight: 700, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: raw.faint,
        fontFamily: fonts.body, marginBottom: 14,
      }}>TYPOGRAPHY</div>

      {/* Heading font */}
      {heading?.family && (
        <div style={{ marginBottom: 14 }}>
          <div style={{
            fontFamily: `'${heading.family}', sans-serif`,
            fontSize: 36, lineHeight: 1.1, color: raw.ink,
            textTransform: 'uppercase', letterSpacing: '0.01em',
            opacity: headingLoaded ? 1 : 0,
            transition: 'opacity 0.4s ease',
            minHeight: headingLoaded ? undefined : 40,
          }}>{sampleName}</div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            marginTop: 8,
          }}>
            <div style={{
              width: 6, height: 6, background: raw.red, flexShrink: 0,
            }} />
            <div style={{
              fontSize: 10, color: raw.muted,
              fontFamily: fonts.mono, letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}>
              {heading.family}
              {heading.style && <span style={{ color: raw.faint }}> · {heading.style}</span>}
              <span style={{ color: raw.faint }}> — Display</span>
            </div>
          </div>
        </div>
      )}

      {/* Separator */}
      <div style={{
        height: 1, background: raw.line, width: '100%',
        marginBottom: 14,
      }} />

      {/* Body font */}
      {body?.family && (
        <div>
          <div style={{
            fontFamily: `'${body.family}', sans-serif`,
            fontSize: 18, lineHeight: 1.5, color: raw.muted,
            fontStyle: 'italic',
            opacity: bodyLoaded ? 1 : 0,
            transition: 'opacity 0.4s ease',
            minHeight: bodyLoaded ? undefined : 28,
          }}>{sampleTagline}</div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            marginTop: 8,
          }}>
            <div style={{
              width: 6, height: 6, border: `1.5px solid ${raw.red}`,
              background: 'transparent', flexShrink: 0,
            }} />
            <div style={{
              fontSize: 10, color: raw.muted,
              fontFamily: fonts.mono, letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}>
              {body.family}
              {body.style && <span style={{ color: raw.faint }}> · {body.style}</span>}
              <span style={{ color: raw.faint }}> — Body</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
