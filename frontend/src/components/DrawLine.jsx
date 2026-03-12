import { useState, useEffect } from 'react';

export default function DrawLine({ direction = 'horizontal', delay = 0, color = 'rgba(0,0,0,0.06)', thickness = 1 }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDrawn(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  const isV = direction === 'vertical';
  return (
    <div style={{
      position: 'absolute',
      [isV ? 'width' : 'height']: thickness,
      [isV ? 'height' : 'width']: drawn ? '100%' : '0%',
      background: color,
      transition: 'all 1.2s cubic-bezier(0.16,1,0.3,1)',
      transitionDelay: `${delay}ms`,
    }} />
  );
}
