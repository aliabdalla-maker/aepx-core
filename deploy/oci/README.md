# OCI production hosting for AEP-X GUI

AEP-X is hosted directly on the Oracle Cloud Infrastructure server that already serves `softwareequality.com`. Netlify is not part of the production path.

## Production URLs

- `https://softwareequality.com/aep-x/`
- `https://www.softwareequality.com/aep-x/` (redirects to the apex host)

## Actual production stack

The Software Equality site is served by the existing **Caddy** container in `aliabdalla-maker/good-hour`, not Nginx. The AEP-X deployment therefore publishes into a dedicated host path mounted read-only into Caddy:

`GitHub master -> self-hosted GitHub Actions runner on OCI -> /srv/aepx -> Caddy -> softwareequality.com/aep-x/`

The website repository remains independently synced into `/srv/sites/softwareequality-website`; AEP-X is deliberately kept outside that Git checkout so the site's two-minute `git reset --hard` sync cannot remove or overwrite AEP-X releases.

## OCI region

Target region: `uk-london-1`.

## 1. Register the OCI server as a GitHub self-hosted runner

Open:

`https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners/new?arch=x64&os=linux`

Generate a fresh short-lived registration token and register the runner on the OCI host. The production workflow uses GitHub's default Linux x64 labels:

```yaml
runs-on: [self-hosted, linux, x64]
```

No long-lived `OCI_HOST`, `OCI_USER`, or `OCI_SSH_PRIVATE_KEY` secrets are required once the runner is registered.

The supplied helper can be used for one-time installation:

```bash
cd /path/to/aepx-core
chmod +x deploy/oci/install-self-hosted-runner.sh
sudo -v
RUNNER_TOKEN='<short-lived-token>' ./deploy/oci/install-self-hosted-runner.sh
```

Never commit or persist the registration token.

## 2. Caddy integration

The production Caddy configuration lives in:

`aliabdalla-maker/good-hour/deploy/Caddyfile`

It must route `/aep-x/` to `/srv/aepx/current` and the Caddy service must bind-mount:

```yaml
- /srv/aepx:/srv/aepx:ro
```

The runner workflow creates versioned releases under:

```text
/srv/aepx/releases/<git-sha>/
```

and atomically switches:

```text
/srv/aepx/current -> releases/<git-sha>
```

This avoids partial website updates and keeps the five newest releases available on the host.

## 3. Runner permissions

The runner account needs narrowly scoped non-interactive sudo for deployment into `/srv/aepx`: `mkdir`, `rm`, `rsync`, `chmod`, `ln`, `mv`, and `find`.

Do not grant unrestricted passwordless sudo unless that is already an accepted server policy.

## Deployment flow

A push to `master` affecting `platform/ecosystem-tracker/**`, `deploy/oci/**`, or `.github/workflows/deploy-oci.yml` triggers the deployment.

The workflow:

1. validates the static app and required tools,
2. creates a release directory keyed by the Git commit SHA,
3. switches `/srv/aepx/current` atomically,
4. verifies the release files on disk,
5. verifies both public HTTPS URLs contain the AEP-X application.

Caddy does not need to reload for each AEP-X content deployment because it serves the stable `/srv/aepx/current` path through the mounted parent directory.

## DNS and TLS

Current public hosting already serves `softwareequality.com` from the OCI server. Keep the existing DNS and Caddy-managed TLS configuration. Caddy automatically handles certificate issuance and renewal for the configured hostnames.

## Rollback

List recent releases:

```bash
sudo ls -1dt /srv/aepx/releases/*
```

Point `current` at the desired release:

```bash
cd /srv/aepx
sudo ln -sfn releases/<previous-sha> current.next
sudo mv -Tf current.next current
```

Then verify:

```bash
curl -fsSL https://softwareequality.com/aep-x/ | grep -q 'AEP-X'
```

## Runner health

On OCI:

```bash
cd /opt/actions-runner
sudo ./svc.sh status
```

In GitHub:

`https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners`

The Linux x64 runner must appear online with `self-hosted`, `linux`, and `x64` labels.
