"""本地模拟 provider：用 ffmpeg 生成彩色测试片段，不调用任何 API、不花钱。

用途：验证 project.yaml、调试拼接/接力流程、跑测试。
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from .. import media
from .base import VideoProvider


def _color(text: str) -> str:
    return "0x" + hashlib.sha1(text.encode()).hexdigest()[:6]


class MockProvider(VideoProvider):
    name = "mock"
    model = "mock"
    max_clip_seconds = 15

    def generate_image(self, prompt, out_path, aspect_ratio, reference_images=None):
        w, h = media.dimensions(aspect_ratio, "480p")
        media.run_ffmpeg(["-f", "lavfi", "-i", f"color=c={_color(prompt)}:s={w}x{h}", "-frames:v", "1", str(out_path)])
        return out_path

    def generate_video(self, prompt, out_path, duration, aspect_ratio, resolution, start_image=None):
        w, h = media.dimensions(aspect_ratio, resolution)
        # 每次"拍摄"颜色都不同，模拟真实模型的随机性（重拍后尾帧会变化）
        tint = _color(prompt + uuid.uuid4().hex)
        media.run_ffmpeg([
            "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=24:d={duration}",
            "-f", "lavfi", "-i", f"color=c={tint}@0.5:s={w}x{h}:r=24:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-filter_complex", "[0:v][1:v]overlay[v]",
            "-map", "[v]", "-map", "2:a", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out_path),
        ])
        return out_path
