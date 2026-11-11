"""ClickLab Modal worker for owned/licensed media processing.

Deploy with:
    modal deploy modal_worker.py

This worker is intentionally stateless: input/output live only in the function
container and disappear when the job finishes. The local ClickLab app should
submit jobs through an authenticated adapter; no Modal token belongs in GitHub.
"""
from __future__ import annotations

import base64
import os
import random
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import modal


app = modal.App("clicklab-media-worker")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("numpy")
)


def _params() -> dict:
    return {
        "speed": round(random.uniform(1.012, 1.025), 6),
        "pitch_factor": round(random.uniform(0.982, 0.992), 6),
        "zoom_factor": round(random.uniform(0.94, 0.97), 6),
        "angle": round(random.uniform(0.004, 0.009), 6),
        "lowpass_freq": random.randint(12800, 14200),
        "highpass_freq": random.randint(22, 35),
        "gop_size": random.randint(48, 75),
    }


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode:
        lines = (p.stderr or p.stdout or "FFmpeg failed").splitlines()
        raise RuntimeError(lines[-1][:500] if lines else "FFmpeg failed")


@app.function(image=image, gpu="T4", timeout=3600, scaledown_window=2)
def process_media(input_b64: str, filename: str, quality: str = "720", preset: str = "better2") -> dict:
    """Process one owned/licensed file on a temporary T4 container.

    Returns base64 only for the function API; the eventual ClickLab adapter
    should store the result as a short-lived download object instead of keeping
    it in browser memory.
    """
    if quality not in {"480", "720", "1080"}:
        raise ValueError("quality must be 480, 720 or 1080")
    raw = base64.b64decode(input_b64)
    if not raw or len(raw) > 1024 * 1024 * 1024:
        raise ValueError("input is empty or larger than 1 GB")
    ext = Path(filename or "input.mp4").suffix.lower()
    is_audio = ext in {".mp3", ".wav"}
    p = _params()
    with tempfile.TemporaryDirectory(prefix="clicklab-modal-") as td:
        src = Path(td) / ("input" + (ext if ext else ".mp4")); out = Path(td) / ("output.mp3" if is_audio else "output.mp4")
        src.write_bytes(raw)
        af = (f"asetrate=44100*{p['pitch_factor']},aresample=44100,atempo={p['speed']},"
              "allpass=f=1000:width_type=h:w=200,flanger=delay=2:depth=1:regen=0:width=10:speed=0.2,"
              f"highpass=f={p['highpass_freq']},lowpass=f={p['lowpass_freq']},"
              "extrastereo=m=1.18,acompressor=threshold=-20dB:ratio=1.5:attack=50:release=500")
        if is_audio:
            fc = f"[0:a:0][1:a:0]amix=inputs=2:duration=first[mixed];[mixed]{af}[final]"
            cmd = ["ffmpeg", "-y", "-i", str(src), "-f", "lavfi", "-i", "anoisesrc=c=brown:a=0.004",
                   "-filter_complex", fc, "-map", "[final]", "-map_metadata", "-1", "-vn",
                   "-c:a", "libmp3lame", "-b:a", "192k", str(out)]
            _run(cmd)
        else:
            height = int(quality); width = round(height * 16 / 9 / 2) * 2
            vf = ("hflip,rotate=%s:bilinear=1,crop=iw*%s:ih*%s,scale=%s:%s,"
                  "eq=brightness=0.015:contrast=1.02:saturation=0.96,hue=h=2,"
                  "noise=alls=3:allf=t+u,vignette=PI/6,setpts=PTS/%s") % (
                      p["angle"], p["zoom_factor"], p["zoom_factor"], width, height, p["speed"])
            fc = (f"[0:v:0]{vf}[v];anoisesrc=c=brown:a=0.004[noise];"
                  f"[0:a:0][noise]amix=inputs=2:duration=first[mixed];[mixed]{af}[a]")
            common = ["-y", "-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                      "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact",
                      "-r", "29.97", "-g", str(p["gop_size"]), "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
            nv = ["ffmpeg"] + common[:]
            insert = nv.index("-c:a")
            nv[insert:insert] = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
            try:
                _run(nv)
                encoder = "h264_nvenc"
            except RuntimeError:
                if out.exists(): out.unlink()
                x264 = ["ffmpeg"] + common[:]
                insert = x264.index("-c:a")
                x264[insert:insert] = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
                _run(x264)
                encoder = "libx264-fallback"
        return {"filename": Path(filename).stem + "-modal-better2.0" + out.suffix,
                "quality": quality, "encoder": "libmp3lame" if is_audio else encoder,
                "bytes": out.stat().st_size, "parameters": p,
                "data_b64": base64.b64encode(out.read_bytes()).decode("ascii")}
