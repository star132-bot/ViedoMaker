"""生成流程：关键帧 → 分段视频（尾帧接力）→ 规格统一 + 拼接 → 音乐/字幕 → 发布素材。

所有产物写入 <项目>/output/，状态记录在 output/manifest.json：
- 每段视频都有"指纹"（提示词 + 时长 + 首帧图片内容 + 模型）。
  指纹不变就跳过 → 可断点续跑；改了某个镜头，只有它和依赖它尾帧的后续段落会重新生成。
- 重拍（retake）时旧片段会移到 output/takes/ 保留，方便对比挑选。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import media
from .plan import Segment, plan_segments
from .prompt import keyframe_prompt, reference_images, video_prompt
from .providers.base import VideoProvider
from .schema import Project, Shot

Log = Callable[[str], None]


def _sha(*parts: object) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, Path):
            h.update(p.read_bytes() if p.exists() else b"<missing>")
        else:
            h.update(str(p).encode())
        h.update(b"\0")
    return h.hexdigest()[:16]


@dataclass
class Manifest:
    path: Path
    data: dict = field(default_factory=lambda: {"segments": {}, "keyframes": {}})

    @classmethod
    def load(cls, project: Project) -> "Manifest":
        p = project.output_dir / "manifest.json"
        m = cls(p)
        if p.exists():
            m.data = json.loads(p.read_text(encoding="utf-8"))
        return m

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def segment(self, key: str) -> dict | None:
        return self.data["segments"].get(key)


def _archive(path: Path, takes_dir: Path) -> None:
    if path.exists():
        takes_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), takes_dir / f"{path.stem}_{int(time.time())}{path.suffix}")


def ensure_keyframe(project: Project, shot: Shot, provider: VideoProvider, manifest: Manifest,
                    force: bool = False, log: Log = print) -> Path:
    prompt = keyframe_prompt(project, shot)
    refs = [project.path(r) for r in reference_images(project, shot)]
    fp = _sha(provider.name, getattr(provider, "image_model", provider.model), prompt,
              project.output.aspect_ratio, *refs)
    out = project.output_dir / "keyframes" / f"{shot.id}.png"
    entry = manifest.data["keyframes"].get(shot.id)
    if not force and entry and entry["fingerprint"] == fp and out.exists():
        return out
    _archive(out, project.output_dir / "takes")
    log(f"[关键帧] {shot.id}")
    out.parent.mkdir(parents=True, exist_ok=True)
    provider.generate_image(prompt, out, project.output.aspect_ratio, [r for r in refs if r.exists()])
    manifest.data["keyframes"][shot.id] = {"fingerprint": fp, "path": str(out.relative_to(project.root)),
                                           "prompt": prompt}
    manifest.save()
    return out


def render(project: Project, provider: VideoProvider, only: set[str] | None = None,
           retake: set[str] | None = None, log: Log = print) -> list[Path]:
    """生成所有（或指定的）段落。only/retake 可以填镜头 id（s03）或段落 key（s03.2）。"""
    only, retake = only or set(), retake or set()
    manifest = Manifest.load(project)
    segments = plan_segments(project, provider.max_clip_seconds)
    clips_dir = project.output_dir / "clips"
    prev_last: Path | None = None
    produced: list[Path] = []

    def selected(seg: Segment, names: set[str]) -> bool:
        return seg.key in names or seg.shot.id in names

    for seg in segments:
        entry = manifest.segment(seg.key)
        clip = clips_dir / f"{seg.key}.mp4"

        # 不在本次范围内的段落：沿用已有结果作为接力起点
        if only and not selected(seg, only):
            prev_last = project.root / entry["last_frame"] if entry and clip.exists() else None
            continue

        start = _start_image(project, seg, provider, manifest, prev_last, selected(seg, retake), log)
        prompt = video_prompt(project, seg)
        fp = _sha(provider.name, provider.model, prompt, seg.duration,
                  project.output.aspect_ratio, project.output.resolution, start or "")

        if entry and entry["fingerprint"] == fp and clip.exists() and not selected(seg, retake):
            log(f"[跳过] {seg.key}（已是最新）")
            prev_last = project.root / entry["last_frame"]
            produced.append(clip)
            continue

        _archive(clip, project.output_dir / "takes")
        clip.parent.mkdir(parents=True, exist_ok=True)
        log(f"[生成] {seg.key}  {seg.duration}s  首帧={seg.start_frame}")
        provider.generate_video(prompt, clip, seg.duration, project.output.aspect_ratio,
                                project.output.resolution, start)
        last = media.last_frame(clip, project.output_dir / "frames" / f"{seg.key}_last.png")
        manifest.data["segments"][seg.key] = {
            "fingerprint": fp,
            "shot": seg.shot.id,
            "clip": str(clip.relative_to(project.root)),
            "last_frame": str(last.relative_to(project.root)),
            "start_image": str(start.relative_to(project.root)) if start and start.is_relative_to(project.root) else (str(start) if start else None),
            "prompt": prompt,
            "provider": provider.name,
            "model": provider.model,
            "duration": seg.duration,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        manifest.save()
        prev_last = last
        produced.append(clip)
    return produced


def _start_image(project: Project, seg: Segment, provider: VideoProvider, manifest: Manifest,
                 prev_last: Path | None, force: bool, log: Log) -> Path | None:
    if seg.start_frame == "none":
        return None
    if seg.start_frame == "file":
        p = project.path(seg.shot.start_image or "")
        if not p.exists():
            raise FileNotFoundError(f"镜头 {seg.shot.id} 的首帧图片不存在: {p}")
        return p
    if seg.start_frame == "keyframe":
        return ensure_keyframe(project, seg.shot, provider, manifest, force=force, log=log)
    if prev_last is None or not prev_last.exists():
        raise RuntimeError(f"段落 {seg.key} 需要上一段的尾帧做首帧，但上一段尚未生成。请先生成前面的镜头。")
    return prev_last


def assemble(project: Project, max_seconds: int = 15, log: Log = print) -> Path:
    """把所有段落统一规格、拼接，再加音乐/字幕，输出 output/<id>.mp4。"""
    manifest = Manifest.load(project)
    segments = plan_segments(project, max_seconds)
    w, h = media.dimensions(project.output.aspect_ratio, project.output.resolution)
    norm_dir = project.output_dir / "normalized"
    normalized: list[Path] = []
    cues: list[tuple[float, float, str]] = []
    t = 0.0

    for i, seg in enumerate(segments):
        entry = manifest.segment(seg.key)
        if not entry or not (project.root / entry["clip"]).exists():
            raise RuntimeError(f"段落 {seg.key} 还没有生成，先运行 render")
        src = project.root / entry["clip"]
        prev = segments[i - 1] if i else None
        fade_in = 0.4 if prev and prev.shot.transition == "fade" and seg.part == 1 else 0
        fade_out = 0.4 if seg.shot.transition == "fade" and seg.part == seg.parts else 0
        out = norm_dir / f"{seg.key}.mp4"
        media.normalize(src, out, w, h, project.output.fps, project.audio.keep_clip_audio, fade_in, fade_out)
        d = media.duration(out)
        if seg.shot.dialogue and seg.part == 1:
            shot_len = sum(s.duration for s in segments if s.shot.id == seg.shot.id)
            cues.append((t, t + shot_len, seg.shot.dialogue))
        t += d
        normalized.append(out)

    final = project.output_dir / f"{project.id}.mp4"
    work = media.concat(normalized, project.output_dir / f"{project.id}_concat.mp4")
    if project.audio.music:
        work = media.mix_music(work, project.path(project.audio.music),
                               project.output_dir / f"{project.id}_music.mp4", project.audio.music_volume)
    srt = media.write_srt(cues, project.output_dir / f"{project.id}.srt") if cues else None
    if srt and project.audio.burn_subtitles:
        work = media.burn_subtitles(work, srt, project.output_dir / f"{project.id}_subs.mp4")
    shutil.move(str(work), final)
    for tmp in project.output_dir.glob(f"{project.id}_*.mp4"):
        tmp.unlink()
    _write_publish(project, final)
    log(f"[完成] {final}  时长 {media.duration(final):.1f}s")
    return final


def _write_publish(project: Project, final: Path) -> None:
    """为每个发布平台写一份元数据（标题/简介/标签/文件），供上传脚本或人工使用。"""
    if not project.publish:
        return
    d = project.output_dir / "publish"
    d.mkdir(parents=True, exist_ok=True)
    for target in project.publish:
        meta = target.model_dump()
        meta.update(video=str(final.relative_to(project.root)), aspect_ratio=project.output.aspect_ratio)
        (d / f"{target.platform}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
