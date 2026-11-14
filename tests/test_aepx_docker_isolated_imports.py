"""Exercise the Docker entrypoint import pattern without Docker or execution."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOCKERFILE=(ROOT/"docker/offline-pilot/Dockerfile").read_text()

class DockerIsolatedImports(unittest.TestCase):
    def test_isolated_import_pattern_loads_runner_help(self):
        script_dir=ROOT/"scripts"
        code=("import sys; sys.path.insert(0, "+repr(str(script_dir))+"); "
              "import aepx_supervised_batch; aepx_supervised_batch.main()")
        result=subprocess.run([sys.executable,"-I","-c",code,"--help"],
                              capture_output=True,text=True,timeout=15,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("--checkpoint",result.stdout)
        self.assertIn("--execute",result.stdout)

    def test_dockerfile_retains_isolated_mode_and_explicit_path(self):
        self.assertIn('ENTRYPOINT ["python","-I","-c"',DOCKERFILE)
        self.assertIn("sys.path.insert(0, '/workspace/scripts')",DOCKERFILE)
        self.assertIn("aepx_supervised_batch.main()",DOCKERFILE)

if __name__=="__main__":
    unittest.main()
