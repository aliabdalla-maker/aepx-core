import importlib.util
from pathlib import Path
import unittest
path=Path(__file__).resolve().parents[1]/"deploy/oci/validate-scoped-credentials.py"
spec=importlib.util.spec_from_file_location("scoped_credentials",path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE={"AEPX_REQUIRE_SCOPED_KEYS":"true",
"AEPX_REGISTRY_IDENTITY_KEY":"A"*40,
"AEPX_REGISTRY_WRITE_KEY":"B"*40,
"AEPX_TRUST_WRITE_KEY":"C"*40}
class ScopedCredentialsTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(m.validate(BASE))
    def test_missing_strict_mode(self):
        with self.assertRaises(ValueError):m.validate({**BASE,"AEPX_REQUIRE_SCOPED_KEYS":"false"})
    def test_missing_credential(self):
        with self.assertRaises(ValueError):m.validate({**BASE,"AEPX_TRUST_WRITE_KEY":""})
    def test_duplicate_credentials(self):
        with self.assertRaises(ValueError):m.validate({**BASE,"AEPX_TRUST_WRITE_KEY":BASE["AEPX_REGISTRY_WRITE_KEY"]})
    def test_short_credential(self):
        with self.assertRaises(ValueError):m.validate({**BASE,"AEPX_REGISTRY_IDENTITY_KEY":"short"})
    def test_legacy_key_reuse_denied(self):
        with self.assertRaises(ValueError):
            m.validate({**BASE,"AEPX_INTERNAL_SERVICE_KEY":BASE["AEPX_REGISTRY_WRITE_KEY"]})
    def test_non_url_safe_rejected(self):
        with self.assertRaises(ValueError):
            m.validate({**BASE,"AEPX_REGISTRY_IDENTITY_KEY":"A"*39+"!"})
    def test_overlong_rejected(self):
        with self.assertRaises(ValueError):
            m.validate({**BASE,"AEPX_TRUST_WRITE_KEY":"C"*129})
    def test_duplicate_env_entry_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            env=Path(folder)/".env"
            env.write_text("A=1\nA=2\n")
            with self.assertRaises(ValueError):
                m.effective_env(env,{})
    def test_newline_rejected(self):
        with self.assertRaises(ValueError):m.validate({**BASE,"AEPX_REGISTRY_WRITE_KEY":"B"*40+"\n"})
if __name__=="__main__":unittest.main()
