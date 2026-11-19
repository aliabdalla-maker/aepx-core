# AEP-X GitHub Codespaces development

This development configuration avoids provisioning any Oracle OCI network resources. It uses Docker-in-Docker inside GitHub Codespaces and builds the repository's **existing AEP-X console**, rather than replacing the platform with a starter application.

## Start

1. Open the repository on GitHub and choose **Code → Codespaces → Create codespace** on this branch (or on master after merge).
2. In the Codespaces terminal run:

```bash
bash scripts/codespaces-verify.sh --prerequisites
docker compose -f compose.codespaces.yml up -d --build
bash scripts/codespaces-verify.sh
```

3. Open the **Ports** tab and select port **8083**. Keep port visibility **Private**. Codespaces port forwarding provides the development URL.

## Limitations

The lightweight Compose file starts only the existing AEP-X console. Its backend URLs refer to services that are not started in this mode, so backend-dependent pages/actions may fail or show unavailable status. The verification checks that the console's OpenAPI endpoint responds, **not** that all AEP-X integrations work.

For the entire platform, use the existing `docker-compose.yml` on a sufficiently large host, after reviewing exposed ports and hard-coded development passwords. Do not expose the full stack publicly as-is.

## Troubleshooting

```bash
docker compose -f compose.codespaces.yml ps
docker compose -f compose.codespaces.yml logs --tail=100 aepx-console
docker compose -f compose.codespaces.yml down
```

GitHub Codespaces is an ephemeral development environment, not a production hosting service. OCI's `vcn-count` limit remains unchanged.
