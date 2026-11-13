"""Run disposable PostgreSQL acceptance and fail if tests are skipped."""
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REQUIRED = ("AEPX_TEST_PG_DSN", "AEPX_TEST_PG_RUNTIME_DSN")
if os.environ.get("AEPX_ALLOW_DISPOSABLE_PG_TESTS") != "yes" or any(
    not os.environ.get(key) for key in REQUIRED
):
    raise SystemExit("Disposable PostgreSQL opt-in and both DSNs required")
# The workflow is exclusively for its throwaway local GitHub Actions service.
# Refuse remote hosts or non-test databases even with the opt-in flag set.
for key in REQUIRED:
    try:
        parsed = urlsplit(os.environ[key])
        safe = (
            parsed.scheme in ("postgres", "postgresql")
            and parsed.hostname in ("127.0.0.1", "localhost", "::1")
            and parsed.path == "/aepx_mcp_test"
            and parsed.username in ("postgres", "aepx_runtime")
        )
    except (ValueError, TypeError):
        safe = False
    if not safe:
        raise SystemExit(f"{key} must target the disposable local aepx_mcp_test database")
suite = unittest.defaultTestLoader.discover(
    str(ROOT / "tests"), pattern="test_mcp_remote_intent_postgres.py"
)
expected = suite.countTestCases()
if expected < 3:
    raise SystemExit(f"Too few PostgreSQL acceptance cases: {expected}")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or result.skipped or result.testsRun != expected:
    raise SystemExit(
        f"PostgreSQL acceptance failed: run={result.testsRun}, "
        f"expected={expected}, skipped={len(result.skipped)}, "
        f"errors={len(result.errors)}, failures={len(result.failures)}"
    )
print(f"Verified {result.testsRun} executed PostgreSQL acceptance cases")
