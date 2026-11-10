import base64
import io
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import clicklab as c

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
b64 = lambda raw: base64.b64encode(raw).decode("ascii")


def sine_wav(seconds=1.0, freq=440.0, rate=48000, amplitude=0.5):
    n = int(seconds * rate)
    frames = b"".join(struct.pack("<h", int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


class AudioEditValidationTests(unittest.TestCase):
    def payload(self, **extra):
        return {"rights": True, "b64": b64(b"placeholder"), **extra}

    def test_rights_confirmation_required(self):
        r = c.local_audio_edit({"b64": b64(b"placeholder")})
        self.assertIn("Confirm", r["error"])

    def test_empty_input_rejected(self):
        self.assertIn("empty", c.local_audio_edit({"rights": True, "b64": ""})["error"])

    def test_invalid_options_rejected_before_processing(self):
        cases = [{"format": "flac"}, {"loudness": "-99"}, {"highpass": 50}, {"eq": "mega"},
                 {"fade_in": 31}, {"fade_out": -1}, {"volume": 4}, {"trim_start": 2, "trim_end": 1}]
        for extra in cases:
            r = c.local_audio_edit(self.payload(**extra))
            self.assertIn("error", r, extra)

    @unittest.skipUnless(FFMPEG, "ffmpeg not installed")
    def test_non_audio_file_rejected(self):
        r = c.local_audio_edit(self.payload(b64=b64(b"this is definitely not audio")))
        self.assertIn("decoded as audio", r["error"])


@unittest.skipUnless(FFMPEG and c.np is not None, "ffmpeg/numpy not installed")
class AudioEditRoundTripTests(unittest.TestCase):
    def test_wav_cleanup_reports_real_measurements(self):
        r = c.local_audio_edit({"rights": True, "name": "my tone.wav", "b64": b64(sine_wav(amplitude=0.9)),
                                "denoise": True, "highpass": 80, "eq": "voice", "loudness": "-16",
                                "fade_in": 0.1, "fade_out": 0.1, "format": "wav"})
        self.assertNotIn("error", r, r)
        out = base64.b64decode(r["base64"])
        self.assertEqual(out[:4], b"RIFF")
        self.assertEqual(r["name"], "my tone-cleaned.wav")
        self.assertAlmostEqual(r["before"]["peak_dbfs"], 20 * math.log10(0.9), delta=0.5)
        self.assertEqual(r["before"]["clipped_pct"], 0)
        self.assertIsNotNone(r["after"]["rms_dbfs"])
        self.assertGreater(r["after"]["seconds"], 0.8)
        self.assertLess(r["after"]["seconds"], 1.2)

    def test_mp3_export_with_trim(self):
        r = c.local_audio_edit({"rights": True, "name": "tone", "b64": b64(sine_wav(seconds=2)),
                                "trim_start": 0.5, "trim_end": 1.5, "format": "mp3"})
        self.assertNotIn("error", r, r)
        out = base64.b64decode(r["base64"])
        self.assertTrue(out[:3] == b"ID3" or out[0] == 0xFF)
        self.assertEqual(r["format"], "mp3")
        self.assertGreaterEqual(r["after"]["seconds"], 0.8)
        self.assertLessEqual(r["after"]["seconds"], 1.3)

    def test_clipping_is_measured_not_assumed(self):
        x = c.np.clip(2 * c.np.sin(2 * c.np.pi * 440 * c.np.arange(48000) / 48000), -1, 1)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes((x * 32767).astype("<i2").tobytes())
        r = c.local_audio_edit({"rights": True, "b64": b64(buf.getvalue()), "format": "wav", "loudness": "off", "highpass": 0})
        self.assertNotIn("error", r, r)
        self.assertGreater(r["before"]["clipped_pct"], 20)


class VideoEditValidationTests(unittest.TestCase):
    def payload(self, **extra):
        return {"rights": True, "b64": b64(b"placeholder"), **extra}

    def test_rights_confirmation_required(self):
        self.assertIn("Confirm", c.local_video_edit({"b64": b64(b"placeholder")})["error"])

    def test_invalid_new_options_rejected(self):
        for extra in [{"reframe": "4:3"}, {"fade": 11}, {"speed": 5},
                      {"captions": "plain text without timing"}, {"trim_start": 2, "trim_end": 1}]:
            r = c.local_video_edit(self.payload(**extra))
            self.assertIn("error", r, extra)


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe not installed")
class VideoEditRoundTripTests(unittest.TestCase):
    def source_video(self, td):
        src = Path(td) / "source.mp4"
        p = subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src)],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return src.read_bytes()

    def test_normalize_fade_reframe_and_captions(self):
        with tempfile.TemporaryDirectory() as td:
            raw = self.source_video(td)
            srt = "1\n00:00:00,000 --> 00:00:01,000\nHello captions\n"
            r = c.local_video_edit({"rights": True, "name": "clip.mp4", "b64": b64(raw),
                                    "normalize": True, "fade": 0.2, "reframe": "1:1",
                                    "captions": "data:text/plain;base64," + b64(srt.encode("utf-8"))})
            self.assertNotIn("error", r, r)
            out = Path(td) / "out.mp4"
            out.write_bytes(base64.b64decode(r["base64"]))
            probe = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(probe.stdout.strip(), "1080,1080")
            self.assertEqual(r["name"], "clip-edited.mp4")


if __name__ == "__main__":
    unittest.main()