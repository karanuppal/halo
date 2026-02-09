# Terraform (GCP)

This directory contains Terraform for deploying Halo to GCP.

Target architecture (MVP):
- Cloud Run: `api` service
- Cloud Run: `worker` service (later)
- Cloud SQL (Postgres)
- Secret Manager for API keys (OpenAI, etc.)

## Quick Start (Dev)

1. Pick a GCP project and enable required APIs:
- Cloud Run
- Cloud SQL Admin
- Secret Manager

2. Configure Terraform variables:
- `project_id`
- `region`
- container images for `api` and `worker`

3. Plan and apply:

```bash
cd infra/terraform/envs/dev
terraform init
terraform plan
terraform apply
```

## Notes

- These modules are intentionally minimal. Expect iteration once we wire up Cloud Tasks, private networking, and IAM hardening.
- Do not store secrets in Terraform state. Use Secret Manager resources and inject to Cloud Run.
