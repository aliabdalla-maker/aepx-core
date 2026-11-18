"""Generates docs/matrices/*.md from the code so the matrices cannot drift from what is implemented
(DLV-17..20, DLV-10). Run: python tools/gen_matrices.py"""
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(P / "control-plane"), str(P / "detection")]
from app import i18n  # noqa: E402
from app.routers.files import HANDLERS, OPAQUE  # noqa: E402
from app.routers.integrations import INGEST_CATEGORIES, VERIFIED_ADAPTERS  # noqa: E402

out = P / "docs" / "matrices"
out.mkdir(parents=True, exist_ok=True)
cov = i18n.coverage()
rows = "\n".join(f"| {c['locale']} | {c['direction']} | {c['keys_translated']}/{c['keys_total']} | {c['coverage_pct']}% | "
                 f"{c['status']} | {' > '.join(c['fallback_chain'])} |" for c in cov)
done = sum(c["status"] == "complete" for c in cov)
(out / "locale-coverage.md").write_text(
    f"# Locale coverage matrix\n\nGenerated from `shared/i18n/*.json` by `tools/gen_matrices.py`. {done} of 100 catalogue "
    "locales are complete; the rest fall back to English and are reported as unavailable in the console. No machine "
    "translation has been added: each locale needs a translator and per-locale QA (L10N-11) before it is marked complete.\n\n"
    "Locale-aware formatting (dates, numbers, currency, plurals, collation search) uses the browser's Intl APIs for every "
    "locale regardless of translation status (tested for en, de, fr, ar in `web/tests/lib.test.ts`).\n\n"
    "| Locale | Direction | Keys | Coverage | Status | Fallback chain |\n|---|---|---|---|---|---|\n" + rows + "\n")
vrows = "\n".join(f"| {c['locale']} | device-provided (Web Speech API) | not verified | optional (Web Speech API, consent) | not verified |"
                  for c in cov)
(out / "voice-coverage.md").write_text(
    "# Voice coverage matrix\n\nRead-aloud and dictation use the voices installed on the user's device. The console detects, per "
    "locale, which voices exist (`web/lib/voice.ts`, unit-tested mapping for en, tl/fil, no/nb, zh-Hans, and 'none' for sat) "
    "and says so when none is available. No locale has been verified on a real device yet: that needs a device test pass "
    "(VOC-10). Audio download is not offered (speech synthesis output cannot be captured and device voices carry their own "
    "licences). Output-device selection is not possible for browser speech synthesis; the console reports the system default.\n\n"
    "| Locale | TTS source | TTS verified | STT | STT verified |\n|---|---|---|---|---|\n" + vrows + "\n")
hrows = "\n".join(f"| {m} | {'yes' if h['store'] else 'no'} | {'yes' if h['preview'] else 'no'} | {'yes' if h['edit'] else 'no'} | "
                  f"{', '.join(h['convert']) or '—'} | {'tested' if h['verified'] else 'not implemented'} | {h.get('note', '')} |"
                  for m, h in sorted(HANDLERS.items()))
(out / "file-handlers.md").write_text(
    "# File-handler capability matrix\n\nFrom `control-plane/app/routers/files.py` (`HANDLERS`). Every type is stored as an opaque, "
    "malware-scanned, checksummed blob; preview, edit and conversion exist only where listed. Tests: `control-plane/tests/test_files.py`.\n\n"
    "| MIME type | Store | Preview | Edit | Convert to | Status | Note |\n|---|---|---|---|---|---|---|\n" + hrows +
    f"\n| any other type | yes | no | no | — | tested | {OPAQUE['note']} |\n")
crow = "\n".join(f"| {k} | {', '.join(sorted(v))} | webhook ingest (canonical schema) | "
                 f"{'verified_live' if any(a[0] == k for a in VERIFIED_ADAPTERS) else 'test_only at most'} | named provider + credentials + sandbox contract test |"
                 for k, v in sorted(INGEST_CATEGORIES.items()))
(out / "connector-maturity.md").write_text(
    "# Connector maturity matrix\n\nFrom `control-plane/app/routers/integrations.py`. New integrations start as `unavailable`. "
    "An integration can be set to `test_only` (its data is labelled simulation everywhere); `verified_live` is refused until a "
    "provider adapter is registered in `VERIFIED_ADAPTERS` and sandbox-contract, credential and policy evidence is recorded. "
    f"Registered verified adapters in this release: {len(VERIFIED_ADAPTERS)}. Actions that need a provider (suspend account, revoke "
    "sessions, apply traffic policy, verify backup) return a failed outcome with the reason instead of pretending to succeed.\n\n"
    "AEP-X components used: services/governance `/policy/evaluate` (live, exercised by every action test); connector-bus "
    "`/bus/route` to `aepx://connector/ml` (Ollama adapter; tested with a recorded transport, not against a running model).\n\n"
    "| Signal | Accepted categories | Path | Maturity now | Needed for verified_live |\n|---|---|---|---|---|\n" + crow + "\n")
print("matrices written:", sorted(p.name for p in out.iterdir()))
