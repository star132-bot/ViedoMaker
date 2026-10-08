"""provider 注册表。视频模型和图像模型分开选择，再组合成一个 VideoProvider 给流程使用。

视频：grok | mock
图像：openai | grok | mock
"""

from __future__ import annotations

from .base import VideoProvider

VIDEO = ("grok", "mock")
IMAGE = ("openai", "grok", "mock")


def _video(name: str):
    if name == "grok":
        from .grok import GrokProvider
        return GrokProvider()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    raise ValueError(f"未知的视频 provider: {name}（可选：{', '.join(VIDEO)}）")


def _image(name: str, video):
    if name == "openai":
        from .openai_image import OpenAIImageProvider
        return OpenAIImageProvider()
    if name == video.name:
        return video
    return _video(name)


class Combined(VideoProvider):
    """视频走一个模型、图像走另一个模型。"""

    def __init__(self, video, image):
        self.video, self.image = video, image
        self.name = video.name if video is image else f"{video.name}+{image.name}"
        self.model = video.model
        self.image_model = image.model if image is not video else getattr(video, "image_model", video.model)
        self.max_clip_seconds = video.max_clip_seconds

    @property
    def requires_start_image(self) -> bool:
        return getattr(self.video, "requires_start_image", False)

    def generate_image(self, *a, **kw):
        return self.image.generate_image(*a, **kw)

    def generate_video(self, *a, **kw):
        return self.video.generate_video(*a, **kw)


def get_image_provider(name: str):
    """只要图像模型（不初始化视频模型）。"""
    if name == "openai":
        from .openai_image import OpenAIImageProvider
        return OpenAIImageProvider()
    return _video(name)


def default_image_provider(video: str) -> str:
    return "openai" if video == "grok" else video


def get_provider(video: str, image: str | None = None) -> VideoProvider:
    v = _video(video)
    return Combined(v, _image(image or default_image_provider(video), v))


__all__ = ["VideoProvider", "get_provider", "default_image_provider", "get_image_provider", "VIDEO", "IMAGE"]
