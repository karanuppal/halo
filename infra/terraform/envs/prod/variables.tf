variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "api_image" {
  type = string
}

variable "worker_image" {
  type = string
}
