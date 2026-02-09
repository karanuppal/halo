terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "secrets" {
  source     = "../../modules/secrets"
  project_id = var.project_id
}

module "cloudsql" {
  source     = "../../modules/cloudsql"
  project_id = var.project_id
  region     = var.region
  name       = "halo-prod"
}

module "cloudrun" {
  source     = "../../modules/cloudrun"
  project_id = var.project_id
  region     = var.region

  api_name    = "halo-api"
  api_image   = var.api_image
  worker_name = "halo-worker"
  worker_image = var.worker_image

  cloudsql_instance_connection_name = module.cloudsql.connection_name

  openai_api_key_secret_id = module.secrets.openai_api_key_secret_id
}
