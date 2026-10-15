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
        sec = sk["sections"][0]
        sec["bass"] = [{"at": 0, "note": "C2", "len": 4}, {"at": 0, "note": "H9", "len": 1}]
        sec["chords"] = [{"at": 0, "name": "Cm7", "len": 16}]
        out = self.api.save_sketch("a", sk)
        self.assertEqual(len(out["warnings"]), 1)
        again = self.api.open_sketch("a")["sketch"]["sections"][0]
        self.assertEqual(again["bass"], [{"at": 0, "note": "C2", "len": 4}])
        self.assertEqual(len(again["drums"]["kick"]), 16 * again["bars"])
        text = (self.tmp / "Sketch" / "a.sketch.json").read_text(encoding="utf-8")
        self.assertNotIn('"sections"', text)          # セクションが 1 つなら、前の版と同じ形で書く

    def test_sections(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        sk = self.api.new_sketch("song")["sketch"]
        base = sk["sections"][0]
        sk["sections"] = [{**base, "name": "イントロ", "bars": 4}, {**base, "name": "Aメロ", "bars": 8},
                          {**base, "name": "サビ", "bars": 4}]
        self.api.save_sketch("song", sk)
        text = (self.tmp / "Sketch" / "song.sketch.json").read_text(encoding="utf-8")
        self.assertIn('"sections"', text)
        json.loads(text)                               # 人が読める形でも、JSON として正しい
        got = self.api.open_sketch("song")["sketch"]["sections"]
        self.assertEqual([(s["name"], s["bars"]) for s in got], [("イントロ", 4), ("Aメロ", 8), ("サビ", 4)])
        self.assertEqual(len(got[1]["drums"]["kick"]), 16 * 8)   # 短いパターンは小節の数まで伸ばす
        out = self.api.export_wav("song", 1)
        with wave.open(out["path"]) as w:              # 16 小節 × 4 拍 × 0.625 秒（BPM 96）＝ 40 秒 + 余韻
            self.assertAlmostEqual(w.getnframes() / 44100, 16 * 4 * 60 / 96 + 1.0, delta=0.05)

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

    def test_sampler_record_process_assign(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        import sys, time
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fake_mic import FakeSoundcard
        fake = FakeSoundcard(tone=0, speed=8)
        self.api.mic_backend = fake

        def wait():
            for _ in range(200):
                st = self.api.mic_state()
                if st["phase"] == "idle":
                    return st
                time.sleep(0.02)
            self.fail("録音が終わらない")

        self.assertTrue(self.api.mic_state()["available"])
        self.api.noise_start()                       # 部屋の雑音を 2 秒
        st = wait()
        self.assertIsNotNone(st["noise"])
        self.assertTrue((self.tmp / "data" / "noise.npy").exists())
        fake.tone = 1200.0                           # ガラスを叩く
        self.api.rec_start()
        time.sleep(0.25)
        st = self.api.rec_stop()
        st = wait()
        self.assertGreater(st["raw"], 1.0)
        r = self.api.sample_process({"length": 1.0})
        self.assertLessEqual(r["duration"], 1.0)
        self.assertEqual(r["root"], "D6")            # 1200 Hz ≒ D6
        self.assertTrue(self.api.blob_path(r["key"]).exists())
        self.assertIsNotNone(st["sources"]["pc"])            # PC の音も同時に録れている
        pc = self.api.sample_process({"source": "pc"})
        self.assertEqual(pc["root"], "A4")                    # 電話越しの声など（440 Hz）
        both = self.api.sample_process({"source": "both"})
        self.assertGreater(both["duration"], 0.5)
        saved = self.api.sample_save("glass", {"length": 1.0}, r["root"])
        self.assertEqual(saved["file"], "glass.wav")
        self.assertEqual(self.api.sample_save("glass", {}, "D6")["file"], "glass (2).wav")   # 上書きしない
        smp = {s["file"]: s for s in self.api.samples()}
        self.assertEqual(smp["glass.wav"]["root"], "D6")
        # 割り当て: メロディとクラップ
        sk = self.api.new_sketch("v")["sketch"]
        sk["voices"] = {"melody": {"sample": "glass.wav", "root": "D6"}, "clap": {"sample": "glass.wav"},
                        "piano": {"sample": "x.wav"}, "bass": {"sample": "../x.wav"}}
        sk["sections"][0]["melody"] = [{"at": 0, "note": "D5", "len": 4}]
        w = self.api.save_sketch("v", sk)["warnings"]
        self.assertEqual(len(w), 2)                  # 知らない枠・フォルダを出る名前は読み飛ばす
        got = self.api.open_sketch("v")["sketch"]["voices"]
        self.assertEqual(set(got), {"melody", "clap"})
        self.assertIn('"voices"', (self.tmp / "Sketch" / "v.sketch.json").read_text(encoding="utf-8"))
        s = smp["glass.wav"]
        key = f"s-melody--12-{s['ver']}-{s['b64']}.wav"         # 1 オクターブ下 → 長さは 2 倍
        p = self.api.blob_path(key)
        with wave.open(str(p)) as a, wave.open(str(self.tmp / "Sketch" / "samples" / "glass.wav")) as b:
            self.assertAlmostEqual(a.getnframes() / b.getnframes(), 2.0, delta=0.01)
        out = self.api.export_wav("v", 1)
        self.assertEqual(out["warnings"], [])
        (self.tmp / "Sketch" / "samples" / "glass.wav").unlink()
        self.assertEqual(len(self.api.export_wav("v", 1)["warnings"]), 2)   # 消えた音は内蔵の音に戻して書き出す
        with self.assertRaises(self.api.SketchError):
            self.api.blob_path(f"s-melody-0-1-{s['b64']}.wav")

    def test_pc_only_when_no_mic(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        import sys, time
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fake_mic import FakeSoundcard
        self.api.mic_backend = FakeSoundcard(speed=8, has_mic=False)
        with self.assertRaises(self.api.SketchError):
            self.api.noise_start()                           # 雑音を測るのはマイクだけ
        self.api.rec_start()
        time.sleep(0.2)
        self.api.rec_stop()
        for _ in range(100):
            st = self.api.mic_state()
            if st["phase"] == "idle":
                break
            time.sleep(0.02)
        self.assertIsNone(st["sources"]["mic"])
        self.assertTrue(st["notes"])                          # マイクが無いことを知らせる
        with self.assertRaises(self.api.SketchError):
            self.api.sample_process({"source": "mic"})
        self.assertEqual(self.api.sample_process({"source": "pc"})["root"], "A4")

    def test_pitch_detection(self):
        if not self.api.state()["numpy"]:
            self.skipTest("numpy なし")
        import numpy as np
        smp = self.api._sampler()
        t = np.arange(44100) / 44100
        for hz, midi in ((110.0, 45), (440.0, 69), (1046.5, 84)):
            x = (np.sin(2 * np.pi * hz * t) + 0.5 * np.sin(4 * np.pi * hz * t)) * np.exp(-t / 0.5)
            self.assertEqual(round(smp.detect_pitch(x)["midi"]), midi)


if __name__ == "__main__":
    unittest.main()
