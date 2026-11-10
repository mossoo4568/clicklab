import base64
import io
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

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


def tone_silence_video(td):
    src = Path(td) / "tone_silence.mp4"
    p = subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
                        "-f", "lavfi", "-i", "aevalsrc='if(between(t,1,2),0,0.5*sin(2*PI*440*t))':d=3:s=48000",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return src.read_bytes()


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

    def test_remove_silence_shortens_output(self):
        with tempfile.TemporaryDirectory() as td:
            raw = tone_silence_video(td)
            r = c.local_video_edit({"rights": True, "name": "gap.mp4", "b64": b64(raw),
                                    "remove_silence": True, "normalize": False})
            self.assertNotIn("error", r, r)
            out = Path(td) / "out.mp4"
            out.write_bytes(base64.b64decode(r["base64"]))
            probe = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=nw=1:nk=1", str(out)],
                                   capture_output=True, text=True, timeout=60)
            dur = float(probe.stdout.strip())
            self.assertLess(dur, 2.7)
            self.assertGreater(dur, 1.5)


class EditPlanHelperTests(unittest.TestCase):
    def test_clamp_ignores_unknown_fields_and_defaults(self):
        e = c._clamp_edit({"evil": "x", "speed": "bad"})
        self.assertNotIn("evil", e)
        self.assertEqual(e["speed"], 1)
        self.assertEqual(e["brightness"], 0)
        self.assertIsNone(e["trim_end"])
        self.assertFalse(e["remove_silence"])

    def test_keep_segments_complements_silence_with_pad(self):
        self.assertEqual(c._keep_segments([[1.0, 2.0]], 3.0), [[0.0, 1.1], [1.9, 3.0]])

    def test_keep_segments_fallback_when_all_silence(self):
        self.assertEqual(c._keep_segments([[0.0, 3.0]], 3.0), [[0.0, 3.0]])

    def test_srt_from_segments_formats_timing_and_skips_blank(self):
        srt = c._srt_from_segments([{"start": 0, "end": 1.5, "text": "Hello"},
                                    {"start": 1.5, "end": 2, "text": "  "}])
        self.assertIn("00:00:00,000 --> 00:00:01,500", srt)
        self.assertIn("Hello", srt)
        self.assertEqual(srt.count("-->"), 1)


class AnalyzeMediaValidationTests(unittest.TestCase):
    def test_rights_confirmation_required(self):
        self.assertIn("Confirm", c.analyze_media({"b64": b64(b"x")})["error"])

    def test_empty_input_rejected(self):
        self.assertIn("empty", c.analyze_media({"rights": True, "b64": ""})["error"])


class PlanMediaEditTests(unittest.TestCase):
    def test_rights_confirmation_required(self):
        self.assertIn("Confirm", c.plan_media_edit({"command": "brighten"})["error"])

    def test_empty_command_rejected(self):
        self.assertIn("Type what", c.plan_media_edit({"rights": True, "command": "  "})["error"])

    def test_missing_key_rejected(self):
        with mock.patch.object(c, "gem_key", return_value=""):
            r = c.plan_media_edit({"rights": True, "command": "brighten"})
        self.assertIn("Gemini key", r["error"])

    def test_plan_is_clamped_to_safe_ranges(self):
        plan = {"edit": {"speed": 9, "brightness": 0.2, "volume": 5, "remove_silence": True,
                         "contrast": 99, "reframe": "4:3", "captions": True}, "reason": "tidy it up"}
        with mock.patch.object(c, "gem_key", return_value="k"), \
             mock.patch.object(c, "gem_try", return_value={"text": json.dumps(plan), "model": "mock"}):
            r = c.plan_media_edit({"rights": True, "command": "speed up and brighten", "analysis": {"duration": 3}})
        self.assertNotIn("error", r, r)
        e = r["edit"]
        self.assertEqual(e["speed"], 4)
        self.assertEqual(e["brightness"], 0.2)
        self.assertEqual(e["volume"], 3)
        self.assertEqual(e["contrast"], 3)
        self.assertEqual(e["reframe"], "none")
        self.assertTrue(e["remove_silence"])
        self.assertTrue(e["captions"])
        self.assertEqual(r["model"], "mock")

    def test_invalid_json_rejected(self):
        with mock.patch.object(c, "gem_key", return_value="k"), \
             mock.patch.object(c, "gem_try", return_value={"text": "sorry, no JSON here", "model": "mock"}):
            r = c.plan_media_edit({"rights": True, "command": "brighten"})
        self.assertIn("JSON", r["error"])

    def test_provider_error_propagated(self):
        with mock.patch.object(c, "gem_key", return_value="k"), \
             mock.patch.object(c, "gem_try", return_value={"error": "quota gone"}):
            r = c.plan_media_edit({"rights": True, "command": "brighten"})
        self.assertEqual(r["error"], "quota gone")


class ImportMediaTests(unittest.TestCase):
    def test_parse_yt_vid_variants(self):
        self.assertEqual(c._parse_yt_vid("dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(c._parse_yt_vid("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10"), "dQw4w9WgXcQ")
        self.assertEqual(c._parse_yt_vid("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(c._parse_yt_vid("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertIsNone(c._parse_yt_vid("https://example.com/foo"))
        self.assertIsNone(c._parse_yt_vid(""))

    def test_rights_confirmation_required(self):
        self.assertIn("Confirm", c.import_media({"url": "https://youtu.be/dQw4w9WgXcQ"})["error"])

    def test_invalid_link_rejected(self):
        self.assertIn("valid YouTube", c.import_media({"rights": True, "url": "https://example.com/x"})["error"])

    def test_download_returns_token_and_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            def fake_run(cmd, **kw):
                out = cmd[cmd.index("-o") + 1]
                Path(out.replace("%(ext)s", "mp4")).write_bytes(b"fake video bytes")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            with mock.patch.object(c, "IMPORT_DIR", Path(td)), \
                 mock.patch.dict(c.MEDIA_IMPORTS, {}, clear=True), \
                 mock.patch.object(c, "find_ytdlp", return_value="yt-dlp"), \
                 mock.patch.object(c.subprocess, "run", side_effect=fake_run):
                r = c.import_media({"rights": True, "url": "https://youtu.be/dQw4w9WgXcQ", "quality": "720"})
                self.assertNotIn("error", r, r)
                self.assertEqual(r["name"], "youtube-dQw4w9WgXcQ.mp4")
                self.assertIn("token", r)
                raw, name, err = c._media_source({"import_token": r["token"]})
                self.assertIsNone(err)
                self.assertEqual(raw, b"fake video bytes")
                self.assertEqual(name, "youtube-dQw4w9WgXcQ.mp4")

    def test_unknown_token_rejected(self):
        with mock.patch.dict(c.MEDIA_IMPORTS, {}, clear=True):
            raw, name, err = c._media_source({"import_token": "nope"})
        self.assertIsNone(raw)
        self.assertIn("expired", err)

    def test_download_failure_propagated(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(c, "IMPORT_DIR", Path(td)), \
                 mock.patch.dict(c.MEDIA_IMPORTS, {}, clear=True), \
                 mock.patch.object(c, "find_ytdlp", return_value="yt-dlp"), \
                 mock.patch.object(c.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "ERROR: video unavailable")):
                r = c.import_media({"rights": True, "url": "https://youtu.be/dQw4w9WgXcQ"})
        self.assertIn("ERROR", r["error"])


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe not installed")
class AnalyzeMediaRoundTripTests(unittest.TestCase):
    def test_non_media_rejected(self):
        r = c.analyze_media({"rights": True, "b64": b64(b"definitely not media"), "transcribe": False})
        self.assertIn("Could not read", r["error"])

    def test_silence_detected_on_tone_silence_tone(self):
        with tempfile.TemporaryDirectory() as td:
            raw = tone_silence_video(td)
            r = c.analyze_media({"rights": True, "b64": b64(raw), "transcribe": False, "silence": True})
            self.assertNotIn("error", r, r)
            self.assertAlmostEqual(r["duration"], 3.0, delta=0.3)
            self.assertTrue(r["silence"], r)
            s, e = r["silence"][0]
            self.assertAlmostEqual(s, 1.0, delta=0.2)
            self.assertAlmostEqual(e, 2.0, delta=0.2)
            self.assertGreater(r["silence_total"], 0.5)
            self.assertIn("audio", r)

    def test_import_token_analysis_and_edit(self):
        with tempfile.TemporaryDirectory() as td:
            raw = tone_silence_video(td)
            f = Path(td) / "imp.mp4"; f.write_bytes(raw)
            with mock.patch.dict(c.MEDIA_IMPORTS, {"tok123": {"path": str(f), "name": "youtube-imp.mp4", "ts": 0, "bytes": len(raw)}}, clear=True):
                a = c.analyze_media({"rights": True, "import_token": "tok123", "transcribe": False, "silence": True})
                self.assertNotIn("error", a, a)
                self.assertAlmostEqual(a["duration"], 3.0, delta=0.3)
                r = c.local_video_edit({"rights": True, "import_token": "tok123", "normalize": False})
                self.assertNotIn("error", r, r)
                self.assertEqual(r["name"], "youtube-imp-edited.mp4")


if __name__ == "__main__":
    unittest.main()