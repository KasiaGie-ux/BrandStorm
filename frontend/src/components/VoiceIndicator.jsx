import { useRef, useEffect, useState } from 'react';
import { raw } from '../styles/tokens';

/**
 * VoiceIndicator — pulsing rings synced to actual agent audio output.
 * Reads frequency data from an AnalyserNode ref.
 */
export default function VoiceIndicator({ analyserRef }) {
  const [level, setLevel] = useState(0);
  const rafRef = useRef(null);

  useEffect(() => {
    const analyser = analyserRef?.current;
    if (!analyser) return;

    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteFrequencyData(data);
      // Average across frequency bins, normalize to 0–1
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      const avg = sum / data.length / 255;
      setLevel(avg);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [analyserRef]);

  const baseSize = 18;
  const scale1 = 1 + level * 0.6;
  const scale2 = 1 + level * 1.2;
  const opacity1 = 0.3 + level * 0.4;
  const opacity2 = 0.15 + level * 0.3;

  return (
    <div style={{
      position: 'relative', width: baseSize, height: baseSize,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }}>
      {/* Outer ring */}
      <div style={{
        position: 'absolute',
        width: baseSize, height: baseSize,
        border: `2px solid ${raw.red}`,
        opacity: opacity2,
        transform: `scale(${scale2})`,
        transition: 'transform 0.08s, opacity 0.08s',
      }} />
      {/* Inner ring */}
      <div style={{
        position: 'absolute',
        width: baseSize, height: baseSize,
        border: `2px solid ${raw.red}`,
        opacity: opacity1,
        transform: `scale(${scale1})`,
        transition: 'transform 0.08s, opacity 0.08s',
      }} />
      {/* Center dot */}
      <div style={{
        width: 6, height: 6,
        background: raw.red,
      }} />
    </div>
  );
}
