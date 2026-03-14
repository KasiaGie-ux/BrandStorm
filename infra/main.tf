terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ── Variables ────────────────────────────────────────────────────────────────

variable "project_id" {
  default = "brandstorm-2026"
}

variable "region" {
  default = "us-central1"
}

variable "image" {
  description = "Container image URL, e.g. gcr.io/brandstorm-2026/brandstorm:latest"
  type        = string
}

variable "gemini_api_key" {
  description = "Developer API key for image gen fallback (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

# ── Provider ─────────────────────────────────────────────────────────────────

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Service Account ───────────────────────────────────────────────────────────

resource "google_service_account" "brandstorm" {
  account_id   = "brandstorm-run"
  display_name = "BrandStorm Cloud Run SA"
}

# Vertex AI — Live API + image generation
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.brandstorm.email}"
}

# Cloud Storage — read/write brand assets
resource "google_project_iam_member" "storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.brandstorm.email}"
}

# ── Storage Buckets ───────────────────────────────────────────────────────────

resource "google_storage_bucket" "uploads" {
  name                        = "bb-uploads-${var.project_id}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 1 }  # product photos — delete after 1 day
  }
}

resource "google_storage_bucket" "assets" {
  name                        = "bb-assets-${var.project_id}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  cors {
    origin          = ["*"]
    method          = ["GET"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# Public read for generated brand assets (frontend fetches images directly)
resource "google_storage_bucket_iam_member" "assets_public_read" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ── Cloud Run ─────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "brandstorm" {
  name     = "brandstorm"
  location = var.region

  template {
    service_account = google_service_account.brandstorm.email

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "UPLOAD_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "ASSETS_BUCKET"
        value = google_storage_bucket.assets.name
      }
      env {
        name  = "USE_GCS"
        value = "true"
      }
      dynamic "env" {
        for_each = var.gemini_api_key != "" ? [1] : []
        content {
          name  = "GEMINI_API_KEY"
          value = var.gemini_api_key
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }
}

# Public access — hackathon, no auth required
resource "google_cloud_run_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.brandstorm.location
  name     = google_cloud_run_v2_service.brandstorm.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "service_url" {
  description = "BrandStorm public URL"
  value       = google_cloud_run_v2_service.brandstorm.uri
}

output "uploads_bucket" {
  value = google_storage_bucket.uploads.name
}

output "assets_bucket" {
  value = google_storage_bucket.assets.name
}
