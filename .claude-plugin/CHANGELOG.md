# aepx-core plugin changelog

Releases are cut with `python scripts/release_plugin.py <patch|minor|major> "summary"` and tagged `plugin-vX.Y.Z`. The marketplace auto-syncs from master, so bump the version for every change to the skills.

## 0.2.1 — 2026-09-27

- Code fixes behind the skills: gateway /health now polls marketplace and billing; aepx-console /api/predict sends the model field ml-integration requires; Jenkinsfile matches CI (all components, same pins, contracts stage); new scripts/gen_connector_catalogue.py regenerates docs/Connector-Catalogue.md (gitlab/dockerhub now specialized) with a CI check. Skills updated to match.

## 0.2.0 — 2026-09-27

- Complete skill set: 45 skills covering every service, the connector bus and all 11 connector categories, SDK, CLI, consoles, blockchain, governance, RFCs/conformance, database, Jenkins, docs and architecture; the original four skills deepened.

## 0.1.0 — 2026-09-27

- First release: marketplace and plugin manifests, plus skills `aepx-run-stack`, `aepx-test-component`, `aepx-connector-adapter` and `aepx-ci-debug`.
