"""Regression: a failed capture must never fall back to a stale frame, and a
remembered capture is snapshotted so the driver cannot overwrite it later."""
import importlib.util, json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_pkg():
    spec = importlib.util.spec_from_file_location(
        "afterimage_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["afterimage_pkg"] = mod
    spec.loader.exec_module(mod)
    return sys.modules["afterimage_pkg.tools"], sys.modules["afterimage_pkg.runtime"]


tools, rt = _load_pkg()


class FakeCtx:
    def __init__(self, result):
        self.result = result

    def dispatch_tool(self, name, args):
        return self.result


class CaptureTests(unittest.TestCase):
    def setUp(self):
        rt.window_geometry = lambda title=None, window_id=None: None  # no X needed
        rt.resolve_pid = lambda window_id=None, title=None: None

    def test_error_does_not_reuse_stale_frame(self):
        rt.last_capture = {"path": "/tmp/old-frame.png"}
        err = json.dumps({"error": "capture failed: window is stale"})
        self.assertIsNone(tools._capture_step(FakeCtx(err), {"pid": 1, "window_id": 2}))

    def test_capture_is_snapshotted(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "computer_use_abc123.png"
            src.write_bytes(b"first")
            tools._remember_capture({}, f"capture mode=vision 10x10 (shareable screenshot saved to {src})")
            snap = Path(rt.last_capture["path"])
            self.assertNotEqual(snap, src)
            src.write_bytes(b"second")  # driver overwrites / reuses the path
            self.assertEqual(snap.read_bytes(), b"first")


if __name__ == "__main__":
    unittest.main()
