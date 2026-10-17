# OCI production hosting for AEP-X GUI

This replaces the previous Netlify deployment path. The production source remains `aliabdalla-maker/aepx-core` on `master`; GitHub Actions deploys the static tracker to the Oracle Cloud Infrastructure server that hosts `softwareequality.com`.

## Production URL

`https://www.softwareequality.com/aep-x/`

The existing Software Equality website remains at `/`. AEP-X is mounted under `/aep-x/` so this deployment does not overwrite the corporate site.

## OCI region

Target account/region: `uk-london-1`.

## One-time server preparation

On the OCI compute instance:

```bash
sudo apt-get update
sudo apt-get install -y nginx rsync
sudo mkdir -p /var/www/softwareequality.com/aep-x
sudo chown -R www-data:www-data /var/www/softwareequality.com
```

Add the contents of `deploy/oci/nginx-aepx-location.conf` inside the existing HTTPS `server { ... }` block for `softwareequality.com` / `www.softwareequality.com`, then run:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Do not replace the existing server block; the snippet is intentionally a location-only configuration so the corporate website stays intact.

## GitHub production secrets

Create these repository or `production` environment secrets:

- `OCI_HOST` — public IP or SSH hostname of the OCI instance
- `OCI_USER` — SSH account, commonly `ubuntu` on Ubuntu images or `opc` on Oracle Linux
- `OCI_SSH_PRIVATE_KEY` — private SSH key whose public key is authorised on the instance

The deploy account needs passwordless sudo for `mkdir`, `rm`, `mv`, `rsync`, `chown`, `nginx -t`, and `systemctl reload nginx`, or an equivalent locked-down deployment mechanism.

## Deployment flow

A push to `master` affecting `platform/ecosystem-tracker/**`, `deploy/oci/**`, or the deployment workflow triggers `.github/workflows/deploy-oci.yml`.

The workflow validates the static app, rsyncs it to the instance, atomically publishes it at `/var/www/softwareequality.com/aep-x`, validates Nginx, reloads Nginx, then checks the public HTTPS URL.

## DNS

If `softwareequality.com` and `www.softwareequality.com` already resolve to this OCI instance, no DNS change is required. If they currently point elsewhere, change their A/AAAA records to the OCI instance public address only after the existing website has also been migrated to the instance.

OCI DNS can host the zone, but it is not required; the registrar or current DNS provider can keep hosting the zone. An A record maps a hostname to an IPv4 address.

## TLS

Keep the existing certificate if the server already terminates HTTPS for the domain. If the OCI instance is new, obtain a certificate for both `softwareequality.com` and `www.softwareequality.com` before moving DNS. Certbot with the Nginx plugin is a common option on Ubuntu.

## Rollback

The deploy keeps the immediately previous release at:

`/var/www/softwareequality.com/aep-x.prev`

Rollback example:

```bash
sudo rm -rf /var/www/softwareequality.com/aep-x.bad
sudo mv /var/www/softwareequality.com/aep-x /var/www/softwareequality.com/aep-x.bad
sudo mv /var/www/softwareequality.com/aep-x.prev /var/www/softwareequality.com/aep-x
sudo nginx -t && sudo systemctl reload nginx
```
