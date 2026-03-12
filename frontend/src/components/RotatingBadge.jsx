import { raw, fonts } from '../styles/tokens';

export default function RotatingBadge({ text = 'BRAND STORM · AI CREATIVE · ', size = 100 }) {
  return (
    <div style={{
      width: size, height: size, position: 'relative',
      animation: 'spin 20s linear infinite',
    }}>
      <svg viewBox="0 0 100 100" style={{ width: '100%', height: '100%' }}>
        <defs>
          <path id="circlePath" d="M 50, 50 m -37, 0 a 37,37 0 1,1 74,0 a 37,37 0 1,1 -74,0" />
        </defs>
        <text style={{
          fontSize: 9.5, letterSpacing: '0.22em', fill: raw.faint,
          fontFamily: fonts.body, fontWeight: 600, textTransform: 'uppercase',
        }}>
          <textPath href="#circlePath">{text}{text}</textPath>
        </text>
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke={raw.red} strokeWidth="2.5" strokeLinecap="round">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
        </svg>
      </div>
    </div>
  );
}
