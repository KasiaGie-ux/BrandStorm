# BrandStorm — Live AI Creative Director

> Upload a product photo. Talk to your creative director. Get a complete brand.

Built for the [Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/) — **Creative Storyteller** category · StellarXLabs · March 2026

---

## What it does

BrandStorm is a live AI creative director powered by Gemini Live API. You upload a product photo, then have a real-time voice conversation with an agent that sees your product, speaks its creative reasoning aloud, and generates a complete brand identity — all in a single session.

**One conversation produces 10 brand assets across 3 modalities:**

| # | Asset | Type |
|---|---|---|
| 1 | Brand name + rationale | Text |
| 2 | Tagline | Text |
| 3 | Brand story | Text |
| 4 | Brand values | Text |
| 5 | Tone-of-voice guide | Text |
| 6 | Logo concept | Image |
| 7 | 5-color palette (HEX) | Image |
| 8 | Hero lifestyle shot | Image |
| 9 | Instagram post (4:5) | Image |
| 10 | Brand story voiceover | Audio |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User (Browser)                          │
│         Voice input (PCM 16kHz) ◄──► Audio output              │
│         Product photo upload    ◄──► Live transcription         │
│         Text fallback input     ◄──► Generated images           │
└───────────────────────┬─────────────────────────────────────────┘
                        │ WebSocket /ws/{session_id}
┌───────────────────────▼─────────────────────────────────────────┐
│                    FastAPI Backend (Cloud Run)                   │
│                                                                 │
│  ┌─────────────────┐     ┌──────────────────────────────────┐   │
│  │  receive_loop   │     │           agent_loop             │   │
│  │                 │     │                                  │   │
│  │ text / audio /  │     │  Live API messages → frontend    │   │
│  │ image upload    │     │  Tool calls → tool_executor      │   │
│  │ → Live API      │     │  PCM keepalive during image gen  │   │
│  └─────────────────┘     └──────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     tool_executor                        │   │
│  │  propose_names · set_brand_identity · set_palette        │   │
│  │  set_fonts · generate_image · generate_voiceover         │   │
│  │  finalize_brand_kit                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────┐   ┌────────────────┐  ┌───────────────┐  │
│  │   BrandCanvas    │   │ ImageGenerator │  │   Voiceover   │  │
│  │  (source of      │   │ Nano Banana Pro│  │  gemini TTS   │  │
│  │   truth)         │   │ + fallback     │  │  Kore voice   │  │
│  └──────────────────┘   └────────────────┘  └───────────────┘  │
└──────────┬────────────────────────┬────────────────────────────┘
           │                        │
┌──────────▼──────────┐  ┌──────────▼──────────────────────────┐
│   Gemini Live API   │  │         Gemini Image Generation     │
│  (Vertex AI)        │  │  gemini-3.1-flash-image-preview     │
│                     │  │  → gemini-2.5-flash-image           │
│  Native Audio       │  │  → gemini-2.0-flash-preview-image   │
│  Vision input       │  │  (3-tier fallback, auto-retry)      │
│  Function calling   │  └─────────────────────────────────────┘
│  Output transcript  │
└─────────────────────┘
```

**Key insight:** The Live API produces `AUDIO` only — no inline images. Images are generated via function calling: the agent invokes `generate_image`, the backend executes against Nano Banana Pro, returns the result to the Live session, and the agent narrates it as part of the conversation.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn, WebSocket |
| Frontend | React 19, Vite 7, Tailwind CSS 4, Motion |
| Audio | Web Audio API, AudioWorklet (PCM capture), Gemini TTS |
| Live Agent | `gemini-live-2.5-flash-native-audio` via Vertex AI (voice + vision + tools) |
| Image Gen | `gemini-3.1-flash-image-preview` (Nano Banana Pro) + 2 fallbacks |
| Voiceover | `gemini-2.5-flash-preview-tts` (Kore voice) |
| Cloud | Google Cloud Run, Vertex AI, Cloud Storage, ADC |
| Container | Docker multi-stage (Node 20 → Python 3.11-slim) |

---

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Docker running locally
- Node.js 20+
- Python 3.11+

**Enable required APIs:**
```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  --project=YOUR_PROJECT_ID
```

---

## Local Development

### 1. Clone and configure

```bash
git clone https://github.com/KasiaGie-ux/BrandStorm.git
cd BrandStorm
```

Create `.env` in the project root (see `.env.example`):

```bash
cp .env.example .env
# then edit .env with your project ID and API key
```

### 2. Backend

```bash
cd backend

pip install -r requirements.txt

# Authenticate with Google Cloud (ADC)
gcloud auth application-default login

python main.py
# Server runs at http://localhost:8080
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# Dev server runs at http://localhost:5173 (proxies API to :8080)
```

Open `http://localhost:5173` in Chrome (required for Web Audio API + AudioWorklet).

---

## Deploy to Cloud Run

One command deploys everything: builds the Docker image, pushes to Artifact Registry, provisions Cloud Storage buckets, sets up IAM, and deploys to Cloud Run.

```bash
./deploy.sh
```

The script:
1. Enables required GCP APIs
2. Creates a `brand-agent` service account with minimal permissions
3. Sets up Artifact Registry and Cloud Storage buckets (7-day TTL)
4. Builds a multi-stage Docker image (frontend → backend/static)
5. Deploys to Cloud Run (2 CPU, 2Gi RAM, min 1 instance)

**Manual deploy (if needed):**
```bash
export PROJECT_ID=your-project-id
export REGION=us-central1

docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/brand-in-a-box/brandstorm .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/brand-in-a-box/brandstorm

gcloud run deploy brandstorm \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/brand-in-a-box/brandstorm \
  --region=$REGION \
  --project=$PROJECT_ID \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=2 --memory=2Gi \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=true"
```

---

## How it works

### Agent flow

```
User uploads photo
       ↓
Agent analyzes product (vision)
       ↓
Agent proposes brand names → propose_names()
       ↓
User chooses name (voice or text)
       ↓
Agent builds identity → set_brand_identity()
       ↓
Agent creates palette → set_palette()
       ↓
Agent selects fonts → set_fonts()
       ↓
Agent generates logo → generate_image("logo")
       ↓
Agent generates hero → generate_image("hero_lifestyle")
       ↓
Agent generates Instagram → generate_image("instagram_post")
       ↓
Agent narrates brand story → generate_voiceover()
       ↓
User clicks "Build my brand kit" → finalize_brand_kit()
       ↓
Download ZIP
```

### BrandCanvas — single source of truth

Every brand element has an explicit status: `EMPTY → GENERATING → READY → STALE`. The agent receives a canvas snapshot on every turn. When the user says "make the palette warmer", the affected elements are marked `STALE` and the agent regenerates only those — downstream assets that depended on the old palette also become stale automatically.

### Image generation fallback chain

```
1. Vertex AI global endpoint — gemini-3.1-flash-image-preview (1 attempt)
2. Google AI Developer API  — same model, up to 4 retries with backoff
3. Vertex AI us-central1   — gemini-2.5-flash-image (4 retries)
4. Vertex AI us-central1   — gemini-2.0-flash-preview-image-generation (4 retries)
```

Preview models on Vertex AI return `RESOURCE_EXHAUSTED` (429) under load. The Developer API fallback is the real workhorse in practice.

---

## Project structure

```
brandstorm/
├── backend/
│   ├── main.py                    # FastAPI app, CORS, static SPA serving
│   ├── config.py                  # All settings from env vars
│   ├── routes/
│   │   ├── ws.py                  # WebSocket endpoint + session lifecycle
│   │   ├── agent_loop.py          # Live API → frontend bridge, tool dispatch
│   │   └── receive_loop.py        # Frontend → Live API, affirmation routing
│   ├── services/
│   │   ├── gemini_live.py         # Live API client, tool declarations, config
│   │   ├── tool_executor.py       # Executes all 7 agent tools
│   │   ├── image_generator.py     # Nano Banana Pro + 3-tier fallback
│   │   ├── voiceover.py           # Gemini TTS brand story narration
│   │   ├── brand_state.py         # In-memory session store
│   │   ├── context_injector.py    # Canvas → agent context message builder
│   │   └── storage.py             # Cloud Storage + local fallback
│   ├── models/
│   │   ├── canvas.py              # BrandCanvas, BrandElement, ElementStatus
│   │   └── session.py             # Session dataclass
│   └── prompts/
│       └── system.py              # Creative Director system prompt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Root: routing, WebSocket, session
│   │   ├── components/            # HeroStage, UploadStage, StudioScreen, ResultsScreen
│   │   └── hooks/                 # useAudioInput, useAudioPlayback, useEventQueue
│   └── public/
│       └── audio-capture.worklet.js  # AudioWorklet for PCM capture
├── Dockerfile                     # Multi-stage: Node 20 build → Python 3.11
└── deploy.sh                      # Full GCP provisioning + Cloud Run deploy
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | `brandstorm-2026` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` | Use Vertex AI (vs Developer API) |
| `LIVE_API_MODEL` | `gemini-live-2.5-flash-native-audio` | Live API model |
| `LIVE_API_VOICE` | `Charon` | Agent voice |
| `IMAGE_MODEL` | `gemini-3.1-flash-image-preview` | Primary image model |
| `GEMINI_API_KEY` | _(empty)_ | Developer API key for image fallback |
| `USE_DEVELOPER_API_FALLBACK` | `true` | Enable Developer API fallback |
| `DEBUG_API_KEY_ONLY` | `false` | Skip Vertex AI for images (local dev) |
| `USE_GCS` | `false` | Use Cloud Storage (vs local filesystem) |

---

## License

MIT
