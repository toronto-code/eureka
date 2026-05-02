terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

variable "project_id" { type = string }
variable "region"     { type = string default = "us-central1" }

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_artifact_registry_repository" "mycelium" {
  location      = var.region
  repository_id = "mycelium"
  format        = "DOCKER"
}

resource "google_sql_database_instance" "mycelium" {
  name             = "mycelium-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "ZONAL"
    backup_configuration { enabled = true }
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }
}

resource "google_sql_database" "mycelium" {
  name     = "mycelium"
  instance = google_sql_database_instance.mycelium.name
}

resource "google_redis_instance" "mycelium" {
  name           = "mycelium-redis"
  tier           = "STANDARD_HA"
  memory_size_gb = 1
  region         = var.region
}

output "registry_repo" {
  value = google_artifact_registry_repository.mycelium.name
}

output "redis_host" {
  value = google_redis_instance.mycelium.host
}

output "sql_connection" {
  value = google_sql_database_instance.mycelium.connection_name
}
