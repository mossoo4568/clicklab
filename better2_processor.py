#!/usr/bin/env python3
"""Better 2.0 local batch studio post-production processor.

Processes owned/licensed .mp3, .wav, .mp4 and .mkv files without modifying the
source directory. Each input receives a fresh set of mastering parameters.
Requires ffmpeg and ffprobe on PATH.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path


AUDIO_EXTS = {".mp3", ".wav"}
VIDEO_EXTS = {".mp4", ".mkv"}


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def random_params(rng: random.Random) -> dict:
    return {
        "speed": round(rng.uniform(1.012, 1.025), 6),
        "pitch_factor": round(rng.uniform(0.982, 0.992), 6),
        "zoom_factor": round(rng.uniform(0.94, 0.97), 6),
        "angle": round(rng.uniform(0.004, 0.009), 6),
        "lowpass_freq": rng.randint(12800, 14200),
        "highpass_freq": rng.randint(22, 35),
        "gop_size": rng.randint(48, 75),
    }


def audio_chain(p: dict) -> str:
    return (
        f"asetrate=44100*{p['pitch_factor']},aresample=44100," 
        f"atempo={p['speed']},"
        "allpass=f=1000:width_type=h:w=200,"
        "flanger=delay=2:depth=1:regen=0:width=10:speed=0.2,"
        f"highpass=f={p['highpass_freq']},lowpass=f={p['lowpass_freq']},"
        "extrastereo=m=1.18,"
        "acompressor=threshold=-20dB:ratio=1.5:attack=50:release=500"
    )


def run(cmd: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def process_audio(src: Path, dst: Path, p: dict) -> dict:
    # Brown noise is mixed as a very low ambient mastering texture.
    fc = (
        f"[0:a:0]{audio_chain(p)}[main];"
        "anoisesrc=c=brown:a=0.004[bed];"
        "[main][bed]amix=inputs=2:duration=first[final]"
    )
    cmd = [ffmpeg_bin(), "-y", "-i", str(src), "-filter_complex", fc,
           "-map", "[final]", "-map_metadata", "-1", "-vn",
           "-c:a", "libmp3lame", "-b:a", "192k", str(dst)]
    result = run(cmd)
    if result.returncode:
        raise RuntimeError(last_error(result))
    return {"kind": "audio", "encoder": "libmp3lame", "parameters": p}


def video_filter(p: dict) -> str:
    return (
        "hflip,"
        f"rotate={p['angle']}:bilinear=1,"
        f"crop=iw*{p['zoom_factor']}:ih*{p['zoom_factor']},"
        "scale=1920:1080,"
        "eq=brightness=0.015:contrast=1.02:saturation=0.96,"
        "hue=h=2,noise=alls=3:allf=t+u,vignette=PI/6,"
        f"setpts=PTS/{p['speed']}"
    )


def process_video(src: Path, dst: Path, p: dict) -> dict:
    af = audio_chain(p)
    fc = (
        f"[0:v:0]{video_filter(p)}[v];"
        f"[0:a:0]{af}[a]"
    )
    common = [ffmpeg_bin(), "-y", "-i", str(src), "-filter_complex", fc,
              "-map", "[v]", "-map", "[a]", "-map_metadata", "-1",
              "-map_chapters", "-1", "-fflags", "+bitexact", "-r", "29.97",
              "-g", str(p["gop_size"]), "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", str(dst)]
    nvenc = common[:]
    nvenc[nvenc.index("-c:a"):nvenc.index("-c:a")] = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
    result = run(nvenc)
    encoder = "h264_nvenc"
    if result.returncode:
        if dst.exists():
            dst.unlink()
        x264 = common[:]
        x264[x264.index("-c:a"):x264.index("-c:a")] = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        result = run(x264)
        encoder = "libx264-fallback"
    if result.returncode:
        raise RuntimeError(last_error(result))
    return {"kind": "video", "encoder": encoder, "parameters": p}


def last_error(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout or "FFmpeg failed").splitlines()
    return lines[-1][:500] if lines else "FFmpeg failed"


def batch_process(source_dir: Path, output_dir: Path, seed: int | None = None, overwrite: bool = False) -> list[dict]:
    if not source_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {source_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    report = []
    for src in sorted(source_dir.iterdir()):
        if not src.is_file() or src.suffix.lower() not in AUDIO_EXTS | VIDEO_EXTS:
            continue
        dst = output_dir / f"{src.stem}-better2.0.mp4" if src.suffix.lower() in VIDEO_EXTS else output_dir / f"{src.stem}-better2.0.mp3"
        if dst.exists() and not overwrite:
            report.append({"input": str(src), "status": "skipped", "output": str(dst)})
            continue
        params = random_params(rng)
        try:
            details = process_audio(src, dst, params) if src.suffix.lower() in AUDIO_EXTS else process_video(src, dst, params)
            report.append({"input": str(src), "output": str(dst), "status": "complete", **details})
        except Exception as exc:
            report.append({"input": str(src), "status": "failed", "error": str(exc), "parameters": params})
    (output_dir / "better2.0-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Better 2.0 batch studio post-production")
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--seed", type=int, help="Optional reproducible test seed")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--rights-confirmed", action="store_true", help="Confirm all inputs are owned/licensed")
    args = ap.parse_args()
    if not args.rights_confirmed:
        ap.error("Pass --rights-confirmed for footage/audio you own or are licensed to edit.")
    report = batch_process(args.input_dir, args.output_dir, args.seed, args.overwrite)
    print(json.dumps(report, indent=2))
    return 0 if all(x["status"] != "failed" for x in report) else 1


if __name__ == "__main__":
    sys.exit(main())
