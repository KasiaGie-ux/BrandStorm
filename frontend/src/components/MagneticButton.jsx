import { useRef, useState } from 'react';
import { raw, fonts } from '../styles/tokens';

export default function MagneticButton({ children, onClick, disabled = false, style = {} }) {
  const ref = useRef(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);

  const handleMove = (e) => {
    if (!ref.current || disabled) return;
    const rect = ref.current.getBoundingClientRect();
    const x = (e.clientX - rect.left - rect.width / 2) * 0.25;
    const y = (e.clientY - rect.top - rect.height / 2) * 0.25;
    setOffset({ x, y });
  };

  return (
    <div
      ref={ref}
      onMouseMove={handleMove}
      onMouseEnter={() => !disabled && setHovered(true)}
      onMouseLeave={() => { setHovered(false); setOffset({ x: 0, y: 0 }); }}
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'inline-block',
        transform: `translate(${offset.x}px, ${offset.y}px)`,
        transition: hovered ? 'transform 0.15s ease-out' : 'transform 0.5s cubic-bezier(0.16,1,0.3,1)',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      <div style={{
        padding: '22px 52px',
        border: `2px solid ${raw.ink}`,
        background: hovered ? raw.ink : 'transparent',
        color: hovered ? raw.cream : raw.ink,
        fontSize: 13, fontWeight: 700,
        fontFamily: fonts.body,
        letterSpacing: '0.18em', textTransform: 'uppercase',
        transition: 'all 0.3s ease',
        display: 'flex', alignItems: 'center', gap: 16,
        position: 'relative', overflow: 'hidden',
        ...style,
      }}>
        <div style={{
          position: 'absolute', inset: 0,
          background: raw.ink,
          transform: hovered ? 'translateX(0)' : 'translateX(-101%)',
          transition: 'transform 0.4s cubic-bezier(0.16,1,0.3,1)',
          zIndex: 0,
        }} />
        <span style={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center', gap: 16 }}>
          {children}
          <span style={{
            display: 'inline-block',
            transition: 'transform 0.3s cubic-bezier(0.16,1,0.3,1)',
            transform: hovered ? 'translateX(8px)' : 'translateX(0)',
            fontSize: 18,
          }}>→</span>
        </span>
      </div>
    </div>
  );
}
