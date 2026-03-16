#!/usr/bin/env bash
set -euo pipefail

# === Brand in a Box — Cloud Run Deployment ===
# Usage: ./deploy.sh
# Requires: gcloud CLI authenticated, Docker running

PROJECT_ID="${GCP_PROJECT:-brandstorm-2026}"
REGION="${GCP_REGION:-us-central1}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"
SERVICE_NAME="brandstorm"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/brand-in-a-box/$SERVICE_NAME"
SA_NAME="brand-agent"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "   Deploying Brand in a Box to Cloud Run"
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"

# --- Enable APIs ---
echo "📡 Enabling APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID" --quiet

# --- Service Account ---
echo "   Setting up service account..."
gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" 2>/dev/null || \
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Brand in a Box Agent" \
    --project="$PROJECT_ID"

for ROLE in roles/aiplatform.user roles/storage.admin roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" --quiet --condition=None
done

# --- Artifact Registry ---
echo "   Setting up Artifact Registry..."
gcloud artifacts repositories describe brand-in-a-box \
  --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || \
  gcloud artifacts repositories create brand-in-a-box \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID"

gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# --- Cloud Storage ---
echo "   Setting up storage buckets..."
for BUCKET in "bb-uploads-$PROJECT_ID" "bb-assets-$PROJECT_ID"; do
  gsutil ls -b "gs://$BUCKET" 2>/dev/null || \
    gsutil mb -l "$REGION" -p "$PROJECT_ID" "gs://$BUCKET"
  gsutil lifecycle set <(echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":7}}]}') "gs://$BUCKET"
done

# --- Build & Push ---
echo "   Building and pushing container..."
docker build -t "$IMAGE" .
docker push "$IMAGE"

# --- Deploy to Cloud Run ---
echo "    Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$SA_EMAIL" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=300 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true${ACCESS_TOKEN:+,ACCESS_TOKEN=$ACCESS_TOKEN}" \
  --quiet

# --- Output ---
URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")
echo ""
echo "   Deployed successfully!"
echo "   URL: $URL"
echo "   Health: $URL/api/health"
