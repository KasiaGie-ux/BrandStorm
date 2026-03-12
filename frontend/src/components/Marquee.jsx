import { raw, fonts } from '../styles/tokens';

const ITEMS = [
  'Brand Strategy', 'Visual Identity', 'Logo Design', 'Voice & Tone',
  'Color Systems', 'Creative Direction', 'Typography', 'Brand Story',
];

export default function Marquee() {
  const repeated = [...ITEMS, ...ITEMS, ...ITEMS, ...ITEMS];
  return (
    <div style={{
      overflow: 'hidden', width: '100vw', marginLeft: '-56px',
      padding: '14px 0',
    }}>
      <div style={{
        display: 'flex', animation: 'marquee 30s linear infinite',
        width: 'max-content',
      }}>
        {repeated.map((item, i) => (
          <span key={i} style={{
            display: 'inline-flex', alignItems: 'center', gap: 20,
            paddingRight: 20, whiteSpace: 'nowrap',
            fontFamily: fonts.display, fontSize: 15,
            color: 'rgba(0,0,0,0.18)', letterSpacing: '0.15em',
            textTransform: 'uppercase',
          }}>
            {item}
            <span style={{ color: raw.red, fontSize: 8 }}>◆</span>
          </span>
        ))}
      </div>
    </div>
  );
}
