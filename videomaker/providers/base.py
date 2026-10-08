"""视频/图像模型的统一接口。接入新模型（可灵、Veo、Runway…）只需实现这个类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VideoProvider(ABC):
    name: str = "base"
    model: str = ""
    max_clip_seconds: int = 15

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        out_path: Path,
        aspect_ratio: str,
        reference_images: list[Path] | None = None,
    ) -> Path:
        """生成一张静态图（关键帧/设定图），写入 out_path 并返回。"""

    @abstractmethod
    def generate_video(
        self,
        prompt: str,
        out_path: Path,
        duration: int,
        aspect_ratio: str,
        resolution: str,
        start_image: Path | None = None,
    ) -> Path:
        """生成一段视频（阻塞直到完成），写入 out_path 并返回。"""
