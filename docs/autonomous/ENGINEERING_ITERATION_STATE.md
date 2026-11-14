# Offline engineering iteration state foundation

This is a **single-writer, offline state machine** for tracking the intended engineering lifecycle. It does not generate code, run an LLM, invoke tools, approve changes or spend money.

Stages are strictly ordered: `requirements → design → patch_proposed → tests_recorded → reviewed → completed`. Each transition requires a nonempty evidence reference (currently a bounded string, **not cryptographically verified**). A second iteration cannot start until the previous iteration is complete. The ledger is atomically replaced and fsynced with a 4 MiB maximum and a 10,000 iteration limit.

**Single-host writer serialization**: callers must use `advance_locked(path, number=..., stage=..., evidence=...)`, which holds the existing exclusive checkpoint lock across `load → advance → persist`. Direct calls to those three primitives remain unsafe for concurrent writers. An abandoned lock requires operator review; do not automatically delete it. Do not connect this module to multiple workers or provider billing. Before integration, add a fenced transactional PostgreSQL state ledger, verifiable artifact digests, immutable append-only audit history, authenticated approvals, durable queue recovery and hard budget reservations. An LLM may propose a patch only inside a disposable isolated worker; it must never self-approve production merges or deployment.

Run offline tests with `python -m unittest discover -s tests -p 'test_aepx_engineering_iteration_state.py' -v`. These tests have been committed but CI has not yet been verified.

This lock is not a distributed lease and does not protect against remote hosts or hostile filesystem races. PostgreSQL fenced state transitions remain mandatory before multi-worker use.

## Offline artifact digest verification

`scripts/aepx_engineering_evidence.py` adds `digest_artifact(root, relative_path)` and `verify_iteration_artifacts(state, number, root, manifest)`. The verifier requires a completed iteration, exactly six stage paths, and matching lowercase SHA-256 digests of regular files within a trusted root. Symlink paths, parent traversal, missing files and files over 2 MiB fail closed.

**Crucial limitation:** existing lifecycle transitions still accept arbitrary evidence references for backward compatibility. Only iterations separately checked by `verify_iteration_artifacts` have digest-verified bytes. A digest does not prove that tests ran, a reviewer approved, or the artifact is trustworthy. Do not count an iteration as verified or authorize deployment based solely on this helper. A signed provenance and approval service with immutable artifact storage is still required. TOCTOU protection on hostile mutable filesystems is also pending.
