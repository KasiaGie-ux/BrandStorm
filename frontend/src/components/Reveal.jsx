import { useState, useEffect } from 'react';

export default function Reveal({ children, delay = 0, from = 'bottom', style = {} }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  const transforms = {
    bottom: visible ? 'translateY(0)' : 'translateY(50px)',
    left: visible ? 'translateX(0)' : 'translateX(-50px)',
    right: visible ? 'translateX(0)' : 'translateX(50px)',
    scale: visible ? 'scale(1)' : 'scale(0.85)',
  };

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: transforms[from],
      transition: 'all 0.9s cubic-bezier(0.16,1,0.3,1)',
      ...style,
    }}>
      {children}
    </div>
  );
}
