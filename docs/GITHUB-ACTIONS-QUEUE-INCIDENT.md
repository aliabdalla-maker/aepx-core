# GitHub Actions queue incident runbook

Run the read-only audit from a trusted workstation:

```bash
python scripts/audit_actions_queue.py --repo aliabdalla-maker/aepx-core
```

Optional: set `GITHUB_TOKEN` using your local secret manager; never
commit it. The script prints run statuses and queued-run ages but makes
no changes to GitHub. The API response is first-page only.

If jobs remain queued, check repository **Settings → Actions → General**
for workflow permissions and Actions enablement; organization policies;
**Settings → Actions → Runners** for online/eligible runners; workflow
`runs-on` labels, concurrency groups, account usage/billing limits and
GitHub Actions service incidents. Use GitHub's UI for actual error
messages and runner assignment. Do not rerun all jobs blindly.

Only count release tests as verified after completed successful workflow
runs and archived test evidence. Do not merge or deploy solely because
the YAML exists.
