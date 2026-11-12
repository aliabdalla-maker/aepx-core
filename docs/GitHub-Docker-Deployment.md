# AEP-X GitHub + Docker deployment (without creating a VCN)

Oracle OCI Resource Manager APPLY failed with `400-LimitExceeded: vcn-count`. GitHub Actions and Docker do **not** bypass OCI networking quotas. This workflow builds the **existing** `platform/aepx-console` application and optionally publishes its image to GitHub Container Registry (GHCR), without invoking Terraform or creating OCI resources.

## Build in GitHub

1. Merge the pull request.
2. Open **Actions → AEP-X Docker build and GHCR publish**.
3. Select **Run workflow**; leave **publish** unchecked to validate/build only.
4. When ready to publish, run again with **publish** checked.
5. The resulting image is `ghcr.io/aliabdalla-maker/aepx-core/aepx-console:latest` (subject to GHCR package visibility and permissions).

## Running the existing full platform

The repository's existing `docker-compose.yml` defines the AEP-X microservices, databases, connectors, and consoles. On a Docker host with adequate memory, disk, and networking:

```bash
git clone https://github.com/aliabdalla-maker/aepx-core.git
cd aepx-core
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps
```

The AEP-X console is mapped to `localhost:8083` by the existing Compose file. The full stack is resource-intensive, and some Compose ports and development credentials are not production-hardened. **Do not expose it publicly without secrets management, authentication, network restrictions, TLS, and security review.**

## OCI note

Deploying on OCI still requires an existing suitable VCN/subnet and an available compute or container host, or an approved service-limit increase. GitHub-hosted runners are temporary CI environments, not persistent production hosting.
