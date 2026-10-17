# OCI production hosting for AEP-X GUI

AEP-X is hosted directly on the Oracle Cloud Infrastructure server for `softwareequality.com`. Netlify is not part of the production path.

## Production URL

Primary URL: `https://softwareequality.com/aep-x/`

Also verify: `https://www.softwareequality.com/aep-x/`

The existing Software Equality website remains at `/`. AEP-X is mounted under `/aep-x/` so deployment does not replace the corporate site.

## OCI region

Target account/region: `uk-london-1`.

## Deployment architecture

`GitHub master -> GitHub Actions -> self-hosted runner on OCI -> local rsync -> Nginx -> softwareequality.com/aep-x/`

No `OCI_HOST`, `OCI_USER`, or `OCI_SSH_PRIVATE_KEY` deployment secrets are required once the self-hosted runner is registered. The only registration credential is GitHub's short-lived runner registration token used during one-time runner setup.

## 1. Register the OCI server as a GitHub self-hosted runner

Open:

`https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners/new`

Generate a registration token, then on the OCI instance run:

```bash
cd /path/to/aepx-core
chmod +x deploy/oci/install-self-hosted-runner.sh
sudo -v
RUNNER_TOKEN='<short-lived-token>' ./deploy/oci/install-self-hosted-runner.sh
```

Do not save the registration token in the repository, shell history, GitHub secrets, or application configuration. It is only needed to register the runner.

The installer labels the runner `oci-aepx`. The production workflow requires:

```yaml
runs-on: [self-hosted, linux, oci-aepx]
```

The runner is installed as a system service so it continues receiving jobs after logout or reboot.

## 2. Configure Nginx

Add the contents of `deploy/oci/nginx-aepx-location.conf` inside the existing HTTPS `server { ... }` block serving `softwareequality.com` and `www.softwareequality.com`.

Then run:

```bash
sudo mkdir -p /var/www/softwareequality.com/aep-x
sudo chown -R www-data:www-data /var/www/softwareequality.com/aep-x
sudo nginx -t
sudo systemctl reload nginx
```

Do not replace the existing server block. The supplied file is a location-only configuration so the existing Software Equality website stays intact.

## 3. Permit local deployment commands

The runner account needs non-interactive sudo for the deployment commands used by `.github/workflows/deploy-oci.yml`: `rm`, `mkdir`, `rsync`, `chown`, `mv`, `nginx -t`, and `systemctl reload nginx`.

Use the narrowest sudoers policy practical for the actual runner username. Do not grant unrestricted passwordless sudo unless that is already an accepted server policy.

## Deployment flow

A push to `master` affecting `platform/ecosystem-tracker/**`, `deploy/oci/**`, or `.github/workflows/deploy-oci.yml` triggers the OCI deployment workflow.

The workflow runs on the OCI host itself, validates the application, stages the current GitHub checkout under `/var/www/softwareequality.com/.aep-x-next`, keeps the previous version as `/var/www/softwareequality.com/aep-x.prev`, reloads Nginx, and verifies both production URLs.

Because the job is local to the OCI host there is no SSH upload step and no OCI private key stored in GitHub Actions.

## DNS and TLS

If `softwareequality.com` and `www.softwareequality.com` already resolve to this OCI instance, no DNS change is required. If they point elsewhere, do not change DNS until the existing Software Equality website is also available from the target OCI server.

Keep the existing TLS certificate if Nginx already serves HTTPS for both hostnames. Otherwise provision a certificate covering both hostnames before switching DNS.

## Rollback

The immediately previous AEP-X release is retained at:

`/var/www/softwareequality.com/aep-x.prev`

Rollback example:

```bash
sudo rm -rf /var/www/softwareequality.com/aep-x.bad
sudo mv /var/www/softwareequality.com/aep-x /var/www/softwareequality.com/aep-x.bad
sudo mv /var/www/softwareequality.com/aep-x.prev /var/www/softwareequality.com/aep-x
sudo nginx -t && sudo systemctl reload nginx
```

## Runner health

On the OCI server:

```bash
cd /opt/actions-runner
sudo ./svc.sh status
```

In GitHub, the runner should appear online with label `oci-aepx` under:

`https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners`
