import pathlib
import subprocess
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/oci/test-staging-postgres.sh"
class StagingDatabaseSmokeTests(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(["bash","-n",str(SCRIPT)],check=True)
    def test_missing_operator_approval_fails_before_docker(self):
        import os
        env={**os.environ,"AEPX_STAGING_APPROVED":"no","PATH":"/usr/bin:/bin"}
        result=subprocess.run(["bash",str(SCRIPT)],cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,3)
        self.assertIn("operator approval",result.stderr)
    def test_explicit_isolated_project(self):
        text=SCRIPT.read_text()
        self.assertIn("-p aepx-oci-staging",text)
        self.assertIn("com.docker.compose.project",text)
        self.assertIn('[[ "$project" == "aepx-oci-staging" && "$service" == "postgres" ]]',text)
    def test_transaction_rolls_back(self):
        text=SCRIPT.read_text()
        self.assertIn("BEGIN;",text)
        self.assertIn("CREATE TEMP TABLE",text)
        self.assertIn("ROLLBACK;",text)
        self.assertNotIn("DROP DATABASE",text)
if __name__=="__main__":unittest.main()
