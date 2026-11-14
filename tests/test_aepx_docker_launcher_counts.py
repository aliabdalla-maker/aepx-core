"""Exercise Docker launcher admission without invoking Docker."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_aepx_offline_docker.sh"
PATTERN = "test_aepx_autonomous_checkpoint.py"

class LauncherCountTests(unittest.TestCase):
    def run_count(self, count):
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                ["bash", str(SCRIPT), "--execute", directory, PATTERN, count],
                capture_output=True, text=True, timeout=5, check=False)

    def test_huge_number_rejected_without_docker(self):
        result = self.run_count("9" * 10000)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Count must be 1..100", result.stderr)

    def test_leading_zero_overlong_rejected(self):
        result = self.run_count("0001")
        self.assertEqual(result.returncode, 2)

    def test_zero_rejected(self):
        result = self.run_count("0")
        self.assertEqual(result.returncode, 2)

    def test_non_digits_rejected(self):
        result = self.run_count("1;echo")
        self.assertEqual(result.returncode, 2)

if __name__ == "__main__":
    unittest.main()
