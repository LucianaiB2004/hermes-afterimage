import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flow as F

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        F.flows_root = lambda: Path(self.tmp.name)  # type: ignore

    def test_roundtrip(self):
        F.save_flow({"name": "monthly-export", "description": "demo", "steps": [{"title": "Click Export"}]})
        got = F.load_flow("monthly-export")
        self.assertEqual(got["name"], "monthly-export")
        self.assertEqual(len(got["steps"]), 1)
        listed = F.list_flows()
        self.assertEqual(listed[0]["name"], "monthly-export")

    def test_missing(self):
        with self.assertRaises(FileNotFoundError):
            F.load_flow("no-such-flow")

if __name__ == "__main__":
    unittest.main()
