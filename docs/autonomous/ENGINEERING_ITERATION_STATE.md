# Offline engineering iteration state foundation

This is a **single-writer, offline state machine** for tracking the intended engineering lifecycle. It does not generate code, run an LLM, invoke tools, approve changes or spend money.

Stages are strictly ordered: `requirements → design → patch_proposed → tests_recorded → reviewed → completed`. Each transition requires a nonempty evidence reference (currently a bounded string, **not cryptographically verified**). A second iteration cannot start until the previous iteration is complete. The ledger is atomically replaced and fsynced with a 4 MiB maximum and a 10,000 iteration limit.

**Single-host writer serialization**: callers must use `advance_locked(path, number=..., stage=..., evidence=...)`, which holds the existing exclusive checkpoint lock across `load → advance → persist`. Direct calls to those three primitives remain unsafe for concurrent writers. An abandoned lock requires operator review; do not automatically delete it. Do not connect this module to multiple workers or provider billing. Before integration, add a fenced transactional PostgreSQL state ledger, verifiable artifact digests, immutable append-only audit history, authenticated approvals, durable queue recovery and hard budget reservations. An LLM may propose a patch only inside a disposable isolated worker; it must never self-approve production merges or deployment.

Run offline tests with `python -m unittest discover -s tests -p 'test_aepx_engineering_iteration_state.py' -v`. These tests have been committed but CI has not yet been verified.

This lock is not a distributed lease and does not protect against remote hosts or hostile filesystem races. PostgreSQL fenced state transitions remain mandatory before multi-worker use.

## Offline artifact digest verification

`scripts/aepx_engineering_evidence.py` adds `digest_artifact(root, relative_path)` and `verify_iteration_artifacts(state, number, root, manifest)`. The verifier requires a completed iteration, exactly six stage paths, and matching lowercase SHA-256 digests of regular files within a trusted root. Symlink paths, parent traversal, missing files and files over 2 MiB fail closed.

**Crucial limitation:** existing lifecycle transitions still accept arbitrary evidence references for backward compatibility. Only iterations separately checked by `verify_iteration_artifacts` have digest-verified bytes. A digest does not prove that tests ran, a reviewer approved, or the artifact is trustworthy. Do not count an iteration as verified or authorize deployment based solely on this helper. A signed provenance and approval service with immutable artifact storage is still required. TOCTOU protection on hostile mutable filesystems is also pending.

## Descriptor-based evidence verification hardening

Evidence hashing now uses POSIX `openat`-style `dir_fd` traversal with `O_NOFOLLOW` on every directory and the final file. It rejects non-regular files via `fstat`, including FIFOs, and caps bytes read. This closes the symlink substitution window between path validation and opening for cooperative local filesystems. It does **not** prevent in-place content modification while hashing, prove immutable storage, or authenticate reviewer identity. Non-POSIX environments without the required flags fail closed.

## Concurrent evidence modification detection

The digest reader now compares device, inode, size, nanosecond modification/change times and bytes read before and after hashing. A detected change fails closed. This is **best-effort detection, not an immutable snapshot**: metadata-preserving writes, unusual filesystems, malicious writers and hash-time races remain possible. Do not use this check as an authorization signal for merge, deployment or billing; use immutable, access-controlled artifacts and authenticated reviewer provenance for that.

## 10,000-iteration ledger capacity

The engineering iteration JSON ledger has an 80 MiB maximum (previously 4 MiB) to accommodate 10,000 completed iterations with six evidence strings each, including worst-case four-byte UTF-8 characters up to the existing 256-character field limit. A regression test builds all 10,000 records, persists and reloads canonical SHA-256 references, and checks worst-case Unicode serialization fits. The 10,000-iteration cap remains enforced.

**Operational warning:** this is a single-host atomic JSON ledger. At high counts every transition serializes the full ledger, which is inefficient and unsuitable for concurrent multi-worker execution. The larger read/write size increases resource usage; use bounded memory and disk capacity, and migrate to PostgreSQL transactional state before autonomous scale-out. This is capacity validation only, not proof of 10,000 executed engineering iterations.
