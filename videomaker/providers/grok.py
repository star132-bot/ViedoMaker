"""xAI Grok Imagine 接入。

注意：以下字段名根据公开资料整理，接入前请以 https://docs.x.ai 为准核对。
所有请求体的拼装都集中在 _video_body / _image_body 两个方法里，改起来只需动这里。

- 视频：POST {base}/videos/generations → {"request_id": ...}
        GET  {base}/videos/{request_id}  → 轮询直到完成，取视频 URL 并立即下载（URL 有时效）
- 图像：POST {base}/images/generations
- 模型：grok-imagine-video（文生视频 + 图生视频）
        grok-imagine-video-1.5（仅图生视频，带同步音频）
- 单段 1–15 秒，480p / 720p
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path

import requests

from .base import VideoProvider

DONE = {"done", "completed", "succeeded", "success"}
FAILED = {"failed", "error", "expired", "cancelled", "canceled"}


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _find_url(obj) -> str | None:
    """在响应中找视频 URL（兼容几种可能的结构）。"""
    if isinstance(obj, dict):
        for key in ("video", "data", "output", "result"):
            if key in obj:
                found = _find_url(obj[key])
                if found:
                    return found
        url = obj.get("url")
        if isinstance(url, str):
            return url
    if isinstance(obj, list):
        for item in obj:
            found = _find_url(item)
            if found:
                return found
    return None


class GrokProvider(VideoProvider):
    name = "grok"
    max_clip_seconds = 15

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        video_model: str | None = None,
        image_model: str | None = None,
        poll_interval: float = 5.0,
        timeout: float = 900.0,
    ):
        self.api_key = api_key or os.environ.get("XAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 XAI_API_KEY 环境变量（见 .env.example）")
        self.base_url = (base_url or os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")).rstrip("/")
        self.model = video_model or os.environ.get("VM_VIDEO_MODEL", "grok-imagine-video")
        self.image_model = image_model or os.environ.get("VM_IMAGE_MODEL", "grok-imagine-image")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    # ---- 请求体：如 API 字段有变化，只改这里 ----
    def _video_body(self, prompt, duration, aspect_ratio, resolution, start_image):
        body = {
            "model": self.model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        if start_image is not None:
            body["image"] = {"url": _data_uri(start_image)}
        return body

    def _image_body(self, prompt, aspect_ratio):
        return {
            "model": self.image_model,
            "prompt": prompt,
            "n": 1,
            "aspect_ratio": aspect_ratio,
            "response_format": "b64_json",
        }

    # ---- 接口实现 ----
    def _post(self, path: str, body: dict) -> dict:
        r = self.session.post(f"{self.base_url}{path}", json=body, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"xAI {path} 返回 {r.status_code}: {r.text[:500]}")
        return r.json()

    def generate_image(self, prompt, out_path, aspect_ratio, reference_images=None):
        # reference_images 暂未使用：Grok 图像接口是否支持参考图请查文档后在此接入
        data = self._post("/images/generations", self._image_body(prompt, aspect_ratio))
        item = data["data"][0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("b64_json"):
            out_path.write_bytes(base64.b64decode(item["b64_json"]))
        else:
            self._download(item["url"], out_path)
        return out_path

    def generate_video(self, prompt, out_path, duration, aspect_ratio, resolution, start_image=None):
        if not 1 <= duration <= self.max_clip_seconds:
            raise ValueError(f"duration 必须在 1–{self.max_clip_seconds} 秒之间，收到 {duration}")
        job = self._post("/videos/generations", self._video_body(prompt, duration, aspect_ratio, resolution, start_image))
        url = _find_url(job)  # 万一是同步返回
        if not url:
            request_id = job.get("request_id") or job.get("id")
            if not request_id:
                raise RuntimeError(f"无法识别的响应: {job}")
            url = self._wait(request_id)
        return self._download(url, out_path)

    def _wait(self, request_id: str) -> str:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            r = self.session.get(f"{self.base_url}/videos/{request_id}", timeout=60)
            r.raise_for_status()
            data = r.json()
            status = str(data.get("status", "")).lower()
            url = _find_url(data)
            if status in FAILED:
                raise RuntimeError(f"视频生成失败 ({status}): {data}")
            if url and (status in DONE or not status):
                return url
            time.sleep(self.poll_interval)
        raise TimeoutError(f"等待视频 {request_id} 超时（{self.timeout}s）")

    def _download(self, url: str, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        return out_path
