import os
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/oci/test-staging-db-commit.sh"
class CommitProbeTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash","-n",str(SCRIPT)],check=True)
    def test_requires_approval_before_docker(self):
        env={**os.environ,"AEPX_STAGING_APPROVED":"no"}
        p=subprocess.run(["bash",str(SCRIPT)],cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,3)
    def test_isolated_project_label(self):
        s=SCRIPT.read_text()
        self.assertIn("-p aepx-oci-staging",s)
        self.assertIn("com.docker.compose.project",s)
        self.assertIn("com.docker.compose.service",s)
    def test_committed_write_then_read_and_cleanup(self):
        s=SCRIPT.read_text()
        self.assertIn("CREATE TABLE",s)
        self.assertIn("SELECT value",s)
        self.assertIn("DROP TABLE IF EXISTS",s)
        self.assertIn("trap cleanup EXIT",s)
    def test_no_container_restart(self):
        s=SCRIPT.read_text()
        self.assertNotIn('compose restart',s)
        self.assertNotIn('compose down',s)
if __name__=="__main__":unittest.main()
