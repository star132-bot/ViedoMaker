from .base import VideoProvider


def get_provider(name: str) -> VideoProvider:
    if name == "grok":
        from .grok import GrokProvider

        return GrokProvider()
    if name == "mock":
        from .mock import MockProvider

        return MockProvider()
    raise ValueError(f"未知的 provider: {name}（可选：grok, mock）")


__all__ = ["VideoProvider", "get_provider"]
