# Frontend rules

## Design system: Editorial Swiss (Brutalist)
- Background: cream #faf6f1 with subtle grid overlay (80px squares, rgba(0,0,0,0.07))
- No glass effects, no blur, no rounded corners. Sharp edges everywhere.
- Cards/containers: 2px solid border (ink or line color), no border-radius, no shadow
- Accent: red #e63946 only. No purple, indigo, emerald, or gradient buttons.
- Typography: Bebas Neue for display/headlines, Syne for body/UI. No Inter, Roboto, or Arial.
- Colors: ink #1a1a1a, muted rgba(0,0,0,0.35), faint rgba(0,0,0,0.15), line rgba(0,0,0,0.07)
- Image tiles: sharp borders (2px solid ink), no border-radius, red label badge top-left, shimmer loading
- Animations: translateY + scale entrance, cubic-bezier(0.16,1,0.3,1) easing
- Red accent stripe: 5px fixed left edge on all screens
- All tokens defined in src/styles/tokens.js (raw, fonts, easeCurve) — use these, not hardcoded values

## Component patterns
- Every component in its own file under src/components/
- WebSocket connection managed via useWebSocket hook in App.jsx
- All images displayed as they arrive (image_generated events), not batched
- Four screens: HeroStage → UploadStage → (LaunchSequence overlay) → StudioScreen → ResultsScreen
- Structured events from backend rendered as specialized components (NameProposals, BrandNameReveal, PaletteReveal, FontSuggestion, etc.)

## Strictly forbidden
- No localStorage or sessionStorage
- No Redux, Zustand, or external state managers
- No rounded corners (border-radius) on cards or containers
- No glass/blur effects (backdrop-blur, saturate)
- No purple, indigo, or emerald colors
- No console.log in production code
