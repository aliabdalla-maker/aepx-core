"""Offline negative tests for the disposable PostgreSQL CI safety gate.

No database connection is made: rejected configurations exit before discovery.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "check_mcp_pg_ci.py"
ADMIN = "postgresql://postgres:disposable-only@127.0.0.1:5432/aepx_mcp_test"
RUNTIME = "postgresql://aepx_runtime:disposable-runtime@127.0.0.1:5432/aepx_mcp_test"

class DisposablePostgresGuardTests(unittest.TestCase):
    def reject(self, **changes):
        env = dict(os.environ)
        env.update({
            "AEPX_ALLOW_DISPOSABLE_PG_TESTS": "yes",
            "AEPX_TEST_PG_DSN": ADMIN,
            "AEPX_TEST_PG_RUNTIME_DSN": RUNTIME,
        })
        env.update(changes)
        result = subprocess.run(
            [sys.executable, str(RUNNER)], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=10, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required" if changes.get("AEPX_ALLOW_DISPOSABLE_PG_TESTS") == "no"
                      else "must target the disposable local", result.stdout + result.stderr)

    def test_refuses_missing_opt_in(self):
        self.reject(AEPX_ALLOW_DISPOSABLE_PG_TESTS="no")

    def test_refuses_remote_admin_host(self):
        self.reject(AEPX_TEST_PG_DSN=ADMIN.replace("127.0.0.1", "db.example.org"))

    def test_refuses_remote_runtime_host(self):
        self.reject(AEPX_TEST_PG_RUNTIME_DSN=RUNTIME.replace("127.0.0.1", "db.example.org"))

    def test_refuses_admin_role_as_runtime(self):
        self.reject(AEPX_TEST_PG_RUNTIME_DSN=ADMIN)

    def test_refuses_runtime_role_as_admin(self):
        self.reject(AEPX_TEST_PG_DSN=RUNTIME)

    def test_refuses_wrong_database(self):
        self.reject(AEPX_TEST_PG_DSN=ADMIN.replace("aepx_mcp_test", "production"))

    def test_refuses_query_override(self):
        self.reject(AEPX_TEST_PG_RUNTIME_DSN=RUNTIME + "?host=db.example.org")

    def test_refuses_wrong_port(self):
        self.reject(AEPX_TEST_PG_RUNTIME_DSN=RUNTIME.replace(":5432/", ":5433/"))

    def test_refuses_missing_password(self):
        self.reject(AEPX_TEST_PG_DSN=ADMIN.replace(":disposable-only@", "@"))

if __name__ == "__main__":
    unittest.main()
