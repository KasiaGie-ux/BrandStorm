import { useState, useEffect } from 'react';
import { raw, fonts } from '../styles/tokens';

export default function TaglineReveal({ tagline }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div style={{
      fontFamily: fonts.body, fontStyle: 'italic',
      fontSize: 18, color: raw.muted, lineHeight: 1.5,
      padding: '4px 0 8px',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(14px)',
      transition: 'all 0.7s cubic-bezier(0.16,1,0.3,1)',
    }}>
      {tagline}
    </div>
  );
}
