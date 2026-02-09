variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

resource "google_sql_database_instance" "postgres" {
  project          = var.project_id
  name             = var.name
  region           = var.region
  database_version = "POSTGRES_15"

  settings {
    tier = "db-f1-micro"
  }
}

output "connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}
