import { Component } from 'react';
import { raw, fonts } from '../styles/tokens';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div style={{
        minHeight: '100vh', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: raw.cream, padding: '40px 24px',
      }}>
        <div style={{
          position: 'fixed', top: 0, left: 0, bottom: 0,
          width: 5, background: raw.red,
        }} />
        <div style={{
          maxWidth: 420, textAlign: 'center',
          border: `2px solid ${raw.line}`,
          padding: '48px 40px', background: 'rgba(255,255,255,0.4)',
        }}>
          <div style={{
            fontFamily: fonts.display, fontSize: 48,
            textTransform: 'uppercase', color: raw.ink,
            lineHeight: 1, marginBottom: 16,
          }}>Oops</div>
          <div style={{
            fontSize: 15, color: raw.muted, fontFamily: fonts.body,
            lineHeight: 1.6, marginBottom: 28,
          }}>
            Something unexpected happened. Refresh to try again.
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              padding: '14px 36px', border: `2px solid ${raw.ink}`,
              background: 'transparent', color: raw.ink,
              fontSize: 13, fontWeight: 700, fontFamily: fonts.body,
              letterSpacing: '0.18em', textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >Refresh</button>
        </div>
      </div>
    );
  }
}
