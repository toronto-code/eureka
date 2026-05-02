# infrastructure/gcloud

Google Cloud deployment configs.

## Targets

- **Cloud Run** for stateless services: `apps/api`, `services/knowledge`, `services/agent-runtime`, `services/integrations`, `services/process-intel`, `services/learning`, `services/security`, `apps/frontend` (static via Cloud Run + nginx).
- **Cloud SQL** (Postgres 16 + `pgvector`) for system-of-record data.
- **Memorystore for Redis** (Standard tier) for the event bus.
- **Artifact Registry** for container images.

## What's here

- `cloudrun/` — one YAML per service, suitable for `gcloud run services replace`.
- `cloudbuild.yaml` — build all images and push to Artifact Registry.
- `terraform/` — minimal Terraform stubs for SQL + Memorystore + Artifact Registry.

These are scaffolds. Tune for your project.

## Conventions

- One Cloud Run service per microservice. They share a single VPC connector to reach Cloud SQL and Memorystore privately.
- `apps/api` is the only ingress that should be public. Other services are private (`--no-allow-unauthenticated`) and reached only by other services via service-to-service auth tokens.
- Neo4j is **not** managed by GCP — run it on a small GCE VM or Neo4j Aura. Update `NEO4J_URI` accordingly.
