"""Tripo3D：从文字或图片生成 3D 模型（GLB），用于 3D 预演。

典型用法：角色设定图 → image_to_model → GLB → 导入 Blender 摆位 → 渲染首帧。

接口（https://platform.tripo3d.ai/docs）：
- POST /v2/openapi/upload        上传图片，返回 image_token
- POST /v2/openapi/task          创建任务 {type: text_to_model | image_to_model, ...}
- GET  /v2/openapi/task/{id}     轮询，status: queued / running / success / failed …
环境变量：TRIPO_API_KEY、TRIPO_BASE_URL（默认 https://api.tripo3d.ai/v2/openapi）
"""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path

import requests

FINAL_FAIL = {"failed", "cancelled", "banned", "expired", "unknown"}


class TripoClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 poll_interval: float = 5.0, timeout: float = 900.0):
        self.api_key = api_key or os.environ.get("TRIPO_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 TRIPO_API_KEY 环境变量（见 .env.example）")
        self.base_url = (base_url or os.environ.get("TRIPO_BASE_URL",
                                                    "https://api.tripo3d.ai/v2/openapi")).rstrip("/")
        self.poll_interval, self.timeout = poll_interval, timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def _check(self, r: requests.Response) -> dict:
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400 or data.get("code", 0) != 0:
            raise RuntimeError(f"Tripo 请求失败 {r.status_code}: {r.text[:500]}")
        return data["data"]

    def balance(self) -> dict:
        return self._check(self.session.get(f"{self.base_url}/user/balance", timeout=30))

    def upload(self, image: Path) -> str:
        mime = mimetypes.guess_type(image.name)[0] or "image/png"
        r = self.session.post(f"{self.base_url}/upload", timeout=120,
                              files={"file": (image.name, image.read_bytes(), mime)})
        data = self._check(r)
        return data.get("image_token") or data["file_token"]

    def create_task(self, body: dict) -> str:
        return self._check(self.session.post(f"{self.base_url}/task", json=body, timeout=60))["task_id"]

    def wait(self, task_id: str, log=print) -> dict:
        deadline = time.monotonic() + self.timeout
        last = None
        while time.monotonic() < deadline:
            data = self._check(self.session.get(f"{self.base_url}/task/{task_id}", timeout=60))
            status = data.get("status")
            if status != last:
                log(f"[3D] {task_id} {status} {data.get('progress', '')}")
                last = status
            if status == "success":
                return data
            if status in FINAL_FAIL:
                raise RuntimeError(f"Tripo 任务失败: {data}")
            time.sleep(self.poll_interval)
        raise TimeoutError(f"等待 Tripo 任务 {task_id} 超时")

    def text_to_model(self, prompt: str, out: Path, log=print, **opts) -> Path:
        task = self.create_task({"type": "text_to_model", "prompt": prompt, **opts})
        return self._download_model(self.wait(task, log), out)

    def image_to_model(self, image: Path, out: Path, log=print, **opts) -> Path:
        token = self.upload(image)
        ext = (image.suffix.lstrip(".") or "png").lower().replace("jpeg", "jpg")
        task = self.create_task({"type": "image_to_model",
                                 "file": {"type": ext, "file_token": token}, **opts})
        return self._download_model(self.wait(task, log), out)

    def _download_model(self, task: dict, out: Path) -> Path:
        output = task.get("output") or {}
        url = output.get("pbr_model") or output.get("model") or output.get("base_model")
        if isinstance(url, dict):
            url = url.get("url")
        if not url:
            raise RuntimeError(f"Tripo 任务没有返回模型地址: {task}")
        out.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        return out
