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

    def _write_wav(self, path, sec=3.0, rate=48000, start=0.5):
        import numpy as np
        t = np.arange(int(sec * rate)) / rate
        x = np.where(t >= start, 0.5 * np.sin(2 * np.pi * 220 * t), 0.0)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes((x * 32767).astype("<i2").tobytes())

    def test_reference_audio(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        outside = self.tmp / "rec-test (clean).wav"
        self._write_wav(outside)
        got = self.api.import_audio(str(outside))
        self.assertEqual(got["file"], "rec-test (clean).wav")
        self.assertIn("rec-test (clean).wav", self.api.state()["audio"])
        info = self.api.ref_info(got["file"])
        self.assertAlmostEqual(info["onset"], 0.5, delta=0.05)          # 無音の後の出だしを見つける
        self.assertTrue(self.api.blob_path(info["key"]).samefile(self.tmp / "Sketch" / got["file"]))
        sk = self.api.new_sketch("r")["sketch"]
        sk["ref"] = {"file": got["file"], "offset": info["onset"], "vol": 0.8, "mute": False}
        self.api.save_sketch("r", sk)
        self.assertEqual(self.api.open_sketch("r")["sketch"]["ref"]["file"], got["file"])
        a = self.api.export_wav("r", 1)
        with wave.open(a["path"]) as w:
            self.assertGreater(w.getnframes(), 44100)
        with self.assertRaises(self.api.SketchError):
            self.api.blob_path("a-" + "Li4vLi4vYm9vdC5pbmk" + ".wav")       # ../../boot.ini は渡さない


if __name__ == "__main__":
    unittest.main()
