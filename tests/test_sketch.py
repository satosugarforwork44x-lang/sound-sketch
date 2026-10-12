"""test_sketch.py — サウンドスケッチの api.py を、Hub を起動せずに確かめる（py -m unittest discover -s tests）。"""
import importlib.util
import json
import tempfile
import unittest
import wave
from pathlib import Path


class _Store:
    def __init__(self):
        self.d = {}

    def get(self, scope, key, default=None):
        return self.d.get((scope, key), default)

    def set(self, scope, key, value):
        self.d[(scope, key)] = json.loads(json.dumps(value))


class _Ctx:
    pass


class SketchTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("hubmod_sketch_test", Path(__file__).resolve().parent.parent / "api.py")
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.tmp = Path(tempfile.mkdtemp())
        ctx = _Ctx()
        ctx.store, ctx.config, ctx.data_dir = _Store(), {}, self.tmp / "data"
        self.api.setup(ctx)
        (self.tmp / "Sketch").mkdir()
        self.api.set_folder(str(self.tmp / "Sketch"))

    def test_roundtrip_and_warnings(self):
        r = self.api.new_sketch("a")
        sk = r["sketch"]
        sk["bass"] = [{"at": 0, "note": "C2", "len": 4}, {"at": 0, "note": "H9", "len": 1}]
        sk["chords"] = [{"at": 0, "name": "Cm7", "len": 16}]
        out = self.api.save_sketch("a", sk)
        self.assertEqual(len(out["warnings"]), 1)
        again = self.api.open_sketch("a")["sketch"]
        self.assertEqual(again["bass"], [{"at": 0, "note": "C2", "len": 4}])
        self.assertEqual(len(again["drums"]["kick"]), 16 * again["bars"])

    def test_unsafe_names_rejected(self):
        for bad in ("../x", "a/b", "c:d"):
            with self.assertRaises(self.api.SketchError):
                self.api.open_sketch(bad)
        with self.assertRaises(self.api.SketchError):
            self.api.blob_path("../../x.wav")

    def test_export_never_overwrites(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        self.api.new_sketch("b")
        a = self.api.export_wav("b", 1)
        b = self.api.export_wav("b", 1)
        self.assertNotEqual(a["path"], b["path"])
        with wave.open(a["path"]) as w:
            self.assertEqual(w.getframerate(), 44100)
            self.assertGreater(w.getnframes(), 44100)


if __name__ == "__main__":
    unittest.main()
