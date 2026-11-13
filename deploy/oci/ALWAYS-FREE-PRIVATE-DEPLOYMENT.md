# AEP-X OCI Always Free — private-first Docker deployment

This is an **optional fresh-install path** for Ubuntu ARM64 on an OCI Ampere A1 Always Free instance. It does not replace the existing production website, Nginx configuration, or GitHub runner deployment.

## Preparation
Provision an OCI Ubuntu A1 instance in your tenancy's eligible region with an Always Free shape and storage. Allow SSH 22 only, ideally restricted to your own IP. Do not open application ports publicly.

On the instance:
```bash
git clone https://github.com/aliabdalla-maker/aepx-core.git /opt/aepx
cd /opt/aepx
git checkout feat/oci-always-free-deployment
sudo bash deploy/oci/prepare-host.sh
```

Create `/opt/aepx/.env` with mode 600 containing `AEPX_POSTGRES_PASSWORD` and `AEPX_NEO4J_PASSWORD` set to different long, random, URL-safe alphanumeric secrets. Never commit the file.

```bash
cd /opt/aepx
chmod 600 .env
bash deploy/oci/deploy.sh
curl -f http://127.0.0.1:8000/health
sudo ss -lntp
```

The deploy script generates a Docker Compose overlay binding published application ports to 127.0.0.1 and adds persistent PostgreSQL storage. Docker Compose v2.24.4+ is required for `!override`.

## Critical release gates
- **Not yet production approved:** existing development Compose contains default credentials and service-to-service DSNs. Review and replace all hardcoded credentials and DSNs before public exposure.
- Validate the full ARM64 image stack and memory footprint (Ollama, Kafka and Neo4j are resource intensive).
- This procedure is intended for **fresh** database initialization. For existing installations, first back up and test restoration; do not change database mounts blindly.
- Use SSH tunnel for private testing: `ssh -L 8083:127.0.0.1:8083 ubuntu@OCI_PUBLIC_IP`; visit `http://localhost:8083`.
- Existing `.github/workflows/ci.yml` remains CI. Do not automatically deploy to production until test, security, backup and rollback gates pass.
- To expose a public URL, add authenticated reverse proxy routing, TLS, domain configuration, rate limits and monitored backups. Verify the existing production `softwareequality.com/aep-x/` route is not disrupted.

## Rollback
Retain the prior reviewed Git commit and a verified off-host database backup. Revert code only when migrations remain compatible; restoring code does not reverse database migrations.
