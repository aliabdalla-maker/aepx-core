# AEP-X Codespaces console + core deployment

Run on the Codespaces feature branch:

```bash
bash scripts/codespaces.sh start
bash scripts/codespaces.sh core
bash scripts/codespaces.sh core-status
bash scripts/codespaces.sh diagnose
```

The console and core use the same external Docker network (`aepx-dev-shared`), allowing DNS resolution of `gateway`, `identity`, `trust`, etc. The full-stack Compose file remains the source of truth for service definitions. The core command starts selected services plus their declared dependencies.

**Security:** The original full-stack Compose publishes multiple service ports and contains hard-coded development credentials. Keep the Codespace and forwarded ports private. Do not expose ports or use this configuration for production. The core command is explicitly opt-in.

**Resources:** A core start can pull Kafka and other heavyweight dependencies. Use a sufficiently large Codespace. A successful console HTTP test does not establish that all backends or MCP connectors are healthy.

**Verification:** `bash scripts/codespaces.sh verify` checks the console HTTP endpoint. `bash scripts/codespaces.sh core-status` checks containers, and `bash scripts/codespaces.sh diagnose` collects diagnostics. Do not merge or deploy publicly without reviewing workflow results and service logs.
