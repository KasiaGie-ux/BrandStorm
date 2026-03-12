import { useState, useEffect } from 'react';
import { raw, fonts } from '../styles/tokens';

function Pill({ value, delay }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <span style={{
      display: 'inline-block',
      padding: '5px 14px',
      border: `2px solid ${raw.red}`,
      color: raw.red,
      fontSize: 10, fontWeight: 700,
      fontFamily: fonts.body, textTransform: 'uppercase',
      letterSpacing: '0.1em',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0) scale(1)' : 'translateY(8px) scale(0.95)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1)',
    }}>
      {value}
    </span>
  );
}

export default function BrandValuesPills({ values = [] }) {
  return (
    <div style={{
      display: 'flex', gap: 8, flexWrap: 'wrap',
      padding: '6px 0',
    }}>
      {values.map((v, i) => (
        <Pill key={i} value={v} delay={100 + i * 120} />
      ))}
    </div>
  );
}
