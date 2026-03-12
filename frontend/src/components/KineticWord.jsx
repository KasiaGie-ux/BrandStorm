import { useState, useEffect } from 'react';
import { raw } from '../styles/tokens';

function KineticLetter({ char, delay, from = 'bottom', color = raw.ink, style = {} }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  const origins = {
    bottom: { from: 'translateY(110%) rotateX(-40deg)', to: 'translateY(0) rotateX(0)' },
    top: { from: 'translateY(-110%) rotateX(40deg)', to: 'translateY(0) rotateX(0)' },
    left: { from: 'translateX(-80px) rotateZ(-10deg)', to: 'translateX(0) rotateZ(0)' },
    right: { from: 'translateX(80px) rotateZ(10deg)', to: 'translateX(0) rotateZ(0)' },
  };

  return (
    <span style={{ display: 'inline-block', overflow: 'hidden', perspective: 400, verticalAlign: 'top' }}>
      <span style={{
        display: 'inline-block',
        transform: visible ? origins[from].to : origins[from].from,
        opacity: visible ? 1 : 0,
        transition: 'transform 0.8s cubic-bezier(0.16,1,0.3,1), opacity 0.5s ease',
        color,
        ...style,
      }}>
        {char === ' ' ? '\u00A0' : char}
      </span>
    </span>
  );
}

export default function KineticWord({ text, baseDelay = 0, stagger = 40, from = 'bottom', color = raw.ink, style = {} }) {
  return (
    <span>
      {text.split('').map((ch, i) => (
        <KineticLetter key={i} char={ch} delay={baseDelay + i * stagger}
          from={from} color={color} style={style} />
      ))}
    </span>
  );
}
