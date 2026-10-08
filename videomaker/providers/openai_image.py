"""OpenAI 兼容的图像生成（关键帧、角色设定图、场景母版）。

两种调用方式（VM_IMAGE_API 切换）：
- images（默认）：POST {base}/images/generations（有参考图时走 /images/edits），
  模型为 VM_IMAGE_MODEL（默认 gpt-image-2.5）。请求 b64_json，图片随响应返回，
  不依赖中转服务的图床域名。
- responses（Codex 方式）：POST {base}/responses，用 image_generation 工具，
  由 VM_IMAGE_CHAT_MODEL 驱动。需要中转服务支持对应的对话模型。

环境变量：OPENAI_API_KEY、OPENAI_BASE_URL（默认 https://api.openai.com/v1）
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path

import requests

SIZES = {  # 画幅 → 生成尺寸
    "16:9": "1536x864", "4:3": "1536x1024",   # 实测支持 1536x864（标准 16:9）
    "9:16": "864x1536", "3:4": "1024x1536",
    "1:1": "1024x1024",
}


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _retry(fn, attempts: int = 4, base_delay: float = 2.0):
    """中转服务偶尔断开连接或返回 5xx：按 2s、4s、8s 退避重试。"""
    for i in range(attempts):
        try:
            r = fn()
            if r.status_code < 500 or i == attempts - 1:
                return r
        except (requests.ConnectionError, requests.Timeout):
            if i == attempts - 1:
                raise
        time.sleep(base_delay * 2 ** i)


class OpenAIImageProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY 环境变量（见 .env.example）")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api = os.environ.get("VM_IMAGE_API", "images")
        self.chat_model = os.environ.get("VM_IMAGE_CHAT_MODEL", "gpt-5.5")
        self.image_model = os.environ.get("VM_IMAGE_MODEL", "gpt-image-2.5")
        self.model = self.chat_model if self.api == "responses" else self.image_model
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def generate_image(self, prompt: str, out_path: Path, aspect_ratio: str,
                       reference_images: list[Path] | None = None) -> Path:
        refs = [r for r in (reference_images or []) if r.exists()]
        size = SIZES.get(aspect_ratio, "1024x1024")
        b64 = (self._via_responses(prompt, size, refs) if self.api == "responses"
               else self._via_images(prompt, size, refs))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(b64))
        return out_path

    def _via_responses(self, prompt: str, size: str, refs: list[Path]) -> str:
        content: list[dict] = [{"type": "input_text", "text": (
            "请生成一张图片，严格按下面的描述。若提供了参考图，人物外貌、服装和画风要与参考图保持一致。\n\n" + prompt)}]
        content += [{"type": "input_image", "image_url": _data_uri(r)} for r in refs]
        body = {
            "model": self.chat_model,
            "input": [{"role": "user", "content": content}],
            "tools": [{"type": "image_generation", "size": size, "quality": "high"}],
            "tool_choice": {"type": "image_generation"},
            "store": False,
        }
        r = _retry(lambda: self.session.post(f"{self.base_url}/responses", json=body, timeout=600))
        if r.status_code >= 400:
            raise RuntimeError(f"图像生成失败 {r.status_code}: {r.text[:500]}")
        for item in r.json().get("output", []):
            if item.get("type") == "image_generation_call" and item.get("result"):
                return item["result"]
        raise RuntimeError(f"响应里没有图片: {r.text[:500]}")

    def _via_images(self, prompt: str, size: str, refs: list[Path]) -> str:
        if refs:
            files = [("image[]", (r.name, r.read_bytes(), mimetypes.guess_type(r.name)[0] or "image/png"))
                     for r in refs]
            r = _retry(lambda: self.session.post(
                f"{self.base_url}/images/edits", timeout=600, files=files,
                data={"model": self.image_model, "prompt": prompt, "size": size,
                      "quality": "high", "response_format": "b64_json"}))
        else:
            r = _retry(lambda: self.session.post(
                f"{self.base_url}/images/generations", timeout=600,
                json={"model": self.image_model, "prompt": prompt, "size": size, "n": 1,
                      "quality": "high", "response_format": "b64_json"}))
        if r.status_code >= 400:
            raise RuntimeError(f"图像生成失败 {r.status_code}: {r.text[:500]}")
        item = r.json()["data"][0]
        if item.get("b64_json"):
            return item["b64_json"]
        try:
            r = _retry(lambda: requests.get(item["url"], timeout=300))
            r.raise_for_status()
            return base64.b64encode(r.content).decode()
        except requests.RequestException as e:
            host = item["url"].split("/")[2]
            raise RuntimeError(f"图片已生成，但中转服务返回的是图床地址 {host}，当前网络无法访问。"
                               f"请在云环境网络设置中放行该域名") from e
