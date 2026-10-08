"""ffmpeg 工具：抽尾帧、探测、规格统一、拼接、混音、字幕。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

HEIGHTS = {"480p": 480, "720p": 720, "1080p": 1080}


def dimensions(aspect_ratio: str, resolution: str) -> tuple[int, int]:
    """按画幅与分辨率（短边）算出宽高，取偶数。"""
    short = HEIGHTS[resolution]
    a, b = (int(x) for x in aspect_ratio.split(":"))
    if a >= b:
        w, h = short * a / b, short
    else:
        w, h = short, short * b / a
    return int(w) // 2 * 2, int(h) // 2 * 2


def run_ffmpeg(args: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("未找到 ffmpeg，请先安装")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {' '.join(cmd)}\n{r.stderr}")


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def has_audio(path: Path) -> bool:
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def last_frame(video: Path, out: Path) -> Path:
    """抽取最后一帧，作为下一段的首帧（尾帧接力）。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-sseof", "-0.5", "-i", str(video), "-map", "0:v:0", "-update", "1", "-q:v", "1", str(out)])
    if not out.exists():  # 极短视频兜底
        run_ffmpeg(["-i", str(video), "-map", "0:v:0", "-vf", "reverse", "-frames:v", "1", str(out)])
    return out


def normalize(src: Path, out: Path, w: int, h: int, fps: int,
              keep_audio: bool = True, fade_in: float = 0, fade_out: float = 0) -> Path:
    """统一分辨率/帧率/编码，并保证有音轨（无声片段补静音），便于拼接。"""
    d = duration(src)
    # 放大铺满后居中裁切：模型输出比例略有偏差（如 Grok 16:9 实为 736x400）时不留黑边
    vf = [f"scale={w}:{h}:force_original_aspect_ratio=increase",
          f"crop={w}:{h}", f"fps={fps}", "setsar=1"]
    af = []
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
        af.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={max(0, d - fade_out):.3f}:d={fade_out}")
        af.append(f"afade=t=out:st={max(0, d - fade_out):.3f}:d={fade_out}")
    use_src_audio = keep_audio and has_audio(src)
    args = ["-i", str(src)]
    if not use_src_audio:
        args += ["-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-vf", ",".join(vf), "-map", "0:v:0", "-map", "0:a:0" if use_src_audio else "1:a:0"]
    if af:
        args += ["-af", ",".join(af)]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(args)
    return out


def concat(clips: list[Path], out: Path) -> Path:
    """拼接已统一规格的片段（concat demuxer，无需重新编码）。"""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    lst.unlink()
    return out


def mix_music(video: Path, music: Path, out: Path, volume: float) -> Path:
    """叠加背景音乐（循环到视频长度，并在结尾淡出）。"""
    d = duration(video)
    run_ffmpeg([
        "-i", str(video), "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        f"[1:a]volume={volume},afade=t=out:st={max(0, d - 2):.3f}:d=2[m];"
        f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-t", f"{d:.3f}", str(out),
    ])
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(cues: list[tuple[float, float, str]], out: Path) -> Path:
    lines = []
    for i, (start, end, text) in enumerate(cues, start=1):
        lines.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def burn_subtitles(video: Path, srt: Path, out: Path) -> Path:
    path = srt.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    run_ffmpeg(["-i", str(video), "-vf", f"subtitles='{path}'", "-c:a", "copy", str(out)])
    return out
