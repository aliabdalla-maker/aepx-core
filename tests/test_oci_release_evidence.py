import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta

path=Path(__file__).resolve().parents[1]/"deploy/oci/validate-release-evidence.py"
spec=importlib.util.spec_from_file_location("release_evidence",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        a=root/"restore.log";b=root/"platform.log"
        a.write_text("restore test succeeded; checksum verified; sample record read\n")
        b.write_text("platform check succeeded; target architecture confirmed\n")
        self.env={
          "AEPX_BACKUP_RESTORE_VERIFIED":"yes",
          "AEPX_IMAGE_PLATFORMS_VERIFIED":"yes",
          "AEPX_BACKUP_RESTORE_EVIDENCE":str(a),
          "AEPX_IMAGE_PLATFORM_EVIDENCE":str(b)}
    def test_valid(self):
        self.assertTrue(m.validate(self.env))
    def test_approval_flag_required(self):
        with self.assertRaises(ValueError):
            m.validate({**self.env,"AEPX_BACKUP_RESTORE_VERIFIED":"no"})
    def test_missing_file_denied(self):
        with self.assertRaises(ValueError):
            m.validate({**self.env,"AEPX_IMAGE_PLATFORM_EVIDENCE":"/nonexistent/oci-evidence"})
    def test_short_file_denied(self):
        Path(self.env["AEPX_IMAGE_PLATFORM_EVIDENCE"]).write_text("ok")
        with self.assertRaises(ValueError):m.validate(self.env)
    def test_stale_file_denied(self):
        p=self.env["AEPX_BACKUP_RESTORE_EVIDENCE"]
        old=time.time()-9*86400
        os.utime(p,(old,old))
        with self.assertRaises(ValueError):m.validate(self.env)
    def test_symlink_denied(self):
        link=Path(self.tmp.name)/"alias.log"
        link.symlink_to(self.env["AEPX_BACKUP_RESTORE_EVIDENCE"])
        with self.assertRaises(ValueError):
            m.validate({**self.env,"AEPX_BACKUP_RESTORE_EVIDENCE":str(link)})
if __name__=="__main__":unittest.main()
