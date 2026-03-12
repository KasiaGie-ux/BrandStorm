import { useState } from 'react';

export default function ParallaxField({ children }) {
  const [mouse, setMouse] = useState({ x: 0.5, y: 0.5 });
  return (
    <div
      onMouseMove={e => setMouse({
        x: e.clientX / window.innerWidth,
        y: e.clientY / window.innerHeight,
      })}
      style={{ position: 'relative', minHeight: '100vh' }}
    >
      {typeof children === 'function' ? children(mouse) : children}
    </div>
  );
}
