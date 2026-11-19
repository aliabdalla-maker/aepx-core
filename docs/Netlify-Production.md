# AEP-X GUI — permanent Netlify deployment from GitHub

The production source of truth is `aliabdalla-maker/aepx-core`, branch `master`.

Netlify configuration is checked into the repository at `/netlify.toml` and publishes:

`platform/ecosystem-tracker`

For the existing Netlify site `aep-x-gui`, configure continuous deployment once with:

- Repository: `aliabdalla-maker/aepx-core`
- Production branch: `master`
- Base directory: repository root
- Build command: none
- Publish directory: `platform/ecosystem-tracker`
- Configuration file: `netlify.toml`

After the site is linked to GitHub, every accepted update to `master` can trigger a production deploy. Use the stable production URL `https://aep-x-gui.netlify.app/`; agent/deploy-specific URLs are previews and should not be treated as the permanent application address.
