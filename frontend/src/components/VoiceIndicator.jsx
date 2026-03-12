import { raw } from '../styles/tokens';

export default function VoiceIndicator({ active = false, size = 36 }) {
  const ringCount = 3;
  return (
    <div style={{
      width: size, height: size, position: 'relative',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {Array.from({ length: ringCount }).map((_, i) => (
        <div key={i} style={{
          position: 'absolute',
          width: size - i * 6, height: size - i * 6,
          borderRadius: '50%',
          border: `1.5px solid ${raw.red}`,
          opacity: active ? 0.4 - i * 0.1 : 0.1,
          transform: active ? `scale(${1 + i * 0.15})` : 'scale(1)',
          transition: 'all 0.4s ease',
          animation: active ? `voicePulse 1.6s ${i * 0.2}s ease-in-out infinite` : 'none',
        }} />
      ))}
      {/* Mic icon */}
      <svg width={size * 0.4} height={size * 0.4} viewBox="0 0 24 24"
        fill="none" stroke={raw.red} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        style={{ position: 'relative', zIndex: 1 }}
      >
        <rect x="9" y="1" width="6" height="11" rx="3" />
        <path d="M19 10v2a7 7 0 01-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
      <style>{`
        @keyframes voicePulse {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.25); opacity: 0.15; }
        }
      `}</style>
    </div>
  );
}
