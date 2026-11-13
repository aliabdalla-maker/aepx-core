import importlib.util
import pathlib
import tempfile
import unittest
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-local-outbox.py"
spec=importlib.util.spec_from_file_location("aepx_local_outbox",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/"outbox.db"
        self.store=m.Outbox(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_idempotent_enqueue(self):
        first=self.store.enqueue("approval.requested",{"id":"x"},"key-1")
        second=m.Outbox(self.path).enqueue("approval.requested",{"id":"x"},"key-1")
        self.assertEqual(first,second)
        self.assertEqual(len(self.store.pending()),1)
    def test_delivery_state(self):
        event=self.store.enqueue("approval.requested",{"id":"x"},"key-2")
        self.assertTrue(self.store.mark_delivered(event))
        self.assertFalse(self.store.mark_delivered(event))
        self.assertEqual(self.store.pending(),[])
    def test_invalid_input(self):
        with self.assertRaises(ValueError):self.store.enqueue("",{},"key")
        with self.assertRaises(ValueError):self.store.pending(0)
if __name__=="__main__":unittest.main()
