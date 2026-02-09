variable "project_id" {
  type = string
}

resource "google_secret_manager_secret" "openai_api_key" {
  project   = var.project_id
  secret_id = "halo-openai-api-key"

  replication {
    auto {}
  }
}

output "openai_api_key_secret_id" {
  value = google_secret_manager_secret.openai_api_key.id
}
