import copy
import importlib.util
from pathlib import Path
import unittest
import yaml
path=Path(__file__).resolve().parents[1]/"deploy/oci/check-staging-policy.py"
spec=importlib.util.spec_from_file_location("staging_policy",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=yaml.safe_load(m.COMPOSE.read_text())
    def test_validate_command_runs_policy_before_docker(self):
        script=(m.ROOT/"deploy/oci/staging.sh").read_text()
        validate=script.split("  --validate)",1)[1].split("    ;;",1)[0]
        self.assertIn("python3 deploy/oci/check-staging-policy.py",validate)
        self.assertLess(validate.index("check-staging-policy.py"),validate.index("config --quiet"))
    def test_real_staging_config(self):
        self.assertEqual(m.check(self.cfg),[])
    def test_public_port_rejected(self):
        self.cfg["services"]["redis"]["ports"]=["6379:6379"]
        self.assertTrue(m.check(self.cfg))
    def test_privileged_rejected(self):
        self.cfg["services"]["identity"]["privileged"]=True
        self.assertTrue(m.check(self.cfg))
    def test_missing_memory_rejected(self):
        self.cfg["services"]["trust"].pop("mem_limit")
        self.assertTrue(m.check(self.cfg))
    def test_excess_memory_rejected(self):
        self.cfg["services"]["postgres"]["mem_limit"]="3000m"
        self.assertTrue(m.check(self.cfg))
    def test_unapproved_service_rejected(self):
        self.cfg["services"]["unknown"]={}
        self.assertTrue(m.check(self.cfg))
    def test_extra_hosts_rejected(self):
        self.cfg["services"]["identity"]["extra_hosts"]=["metadata:169.254.169.254"]
        self.assertTrue(m.check(self.cfg))
    def test_custom_network_mode_rejected(self):
        self.cfg["services"]["redis"]["network_mode"]="bridge"
        self.assertTrue(m.check(self.cfg))
    def test_loopback_service_url_rejected(self):
        self.cfg["services"]["registry"]["environment"]["IDENTITY_URL"]="http://127.0.0.1:8000"
        self.assertTrue(m.check(self.cfg))
    def test_explicit_writable_root_rejected(self):
        self.cfg["services"]["trust"]["read_only"]=False
        self.assertTrue(m.check(self.cfg))
    def test_docker_socket_mount_rejected(self):
        self.cfg["services"]["identity"]["volumes"]=["/var/run/docker.sock:/var/run/docker.sock"]
        self.assertTrue(m.check(self.cfg))
    def test_host_pid_namespace_rejected(self):
        self.cfg["services"]["trust"]["pid"]="host"
        self.assertTrue(m.check(self.cfg))
    def test_host_ipc_namespace_rejected(self):
        self.cfg["services"]["trust"]["ipc"]="host"
        self.assertTrue(m.check(self.cfg))
    def test_extra_capability_rejected(self):
        self.cfg["services"]["registry"]["cap_add"]=["SYS_ADMIN"]
        self.assertTrue(m.check(self.cfg))
    def test_host_device_rejected(self):
        self.cfg["services"]["redis"]["devices"]=["/dev/sda:/dev/sda"]
        self.assertTrue(m.check(self.cfg))
    def test_host_data_bind_rejected(self):
        self.cfg["services"]["postgres"]["volumes"].append("/srv/host-db:/var/lib/postgresql/data")
        self.assertTrue(m.check(self.cfg))
    def test_unmounted_named_volume_rejected(self):
        self.cfg["services"]["postgres"]["volumes"]=["other-volume:/var/lib/postgresql/data"]
        self.assertTrue(m.check(self.cfg))
    def test_missing_volume_rejected(self):
        self.cfg["volumes"].pop("staging-postgres")
        self.assertTrue(m.check(self.cfg))
if __name__=="__main__":unittest.main()
