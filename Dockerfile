# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + static SPA
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev libpng-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy frontend build into backend/static
COPY --from=frontend-build /app/frontend/dist ./static

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
ENV HOST=0.0.0.0
ENV GOOGLE_GENAI_USE_VERTEXAI=true

EXPOSE 8080

CMD ["python", "main.py", "--no-reload"]
