import { useState, useCallback, useRef, useEffect } from 'react';

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&';

export default function ScrambleText({ text, style = {} }) {
  const [display, setDisplay] = useState(text);
  const [isScrambling, setIsScrambling] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    return () => clearInterval(intervalRef.current);
  }, []);

  const scramble = useCallback(() => {
    if (isScrambling) return;
    setIsScrambling(true);
    let iteration = 0;
    intervalRef.current = setInterval(() => {
      setDisplay(text.split('').map((ch, i) => {
        if (ch === ' ') return ' ';
        if (i < iteration) return text[i];
        return CHARS[Math.floor(Math.random() * CHARS.length)];
      }).join(''));
      iteration += 0.5;
      if (iteration >= text.length) {
        clearInterval(intervalRef.current);
        setDisplay(text);
        setIsScrambling(false);
      }
    }, 30);
  }, [text, isScrambling]);

  return (
    <span onMouseEnter={scramble} style={{ cursor: 'default', ...style }}>
      {display}
    </span>
  );
}
