variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "api_name" {
  type = string
}

variable "api_image" {
  type = string
}

variable "worker_name" {
  type = string
}

variable "worker_image" {
  type = string
}

variable "cloudsql_instance_connection_name" {
  type = string
}

variable "openai_api_key_secret_id" {
  type = string
}

resource "google_cloud_run_v2_service" "api" {
  name     = var.api_name
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = var.api_image

      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg://halo@/${var.api_name}?host=/cloudsql/${var.cloudsql_instance_connection_name}"
      }

      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.openai_api_key_secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.cloudsql_instance_connection_name]
      }
    }
  }
}

resource "google_cloud_run_v2_service" "worker" {
  name     = var.worker_name
  location = var.region
  project  = var.project_id

  template {
    containers {
      image = var.worker_image

      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg://halo@/${var.worker_name}?host=/cloudsql/${var.cloudsql_instance_connection_name}"
      }

      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.openai_api_key_secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.cloudsql_instance_connection_name]
      }
    }
  }
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}
