"""用假的 HTTP 会话测试三个服务客户端的请求与解析（不联网）。"""

import base64
from pathlib import Path

import pytest

from videomaker.model3d import TripoClient
from videomaker.providers import get_provider
from videomaker.providers.grok import GrokProvider
from videomaker.providers.openai_image import OpenAIImageProvider

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
        self.text = str(data)

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def _hit(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp(kw) if callable(resp) else resp
        raise AssertionError(f"未预期的请求 {method} {url}")

    def post(self, url, **kw):
        return self._hit("POST", url, **kw)

    def get(self, url, **kw):
        return self._hit("GET", url, **kw)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("TRIPO_API_KEY", "t")
    monkeypatch.setenv("GROK_MODELS_BASE_URL", "https://relay.example/v1")
    monkeypatch.delenv("VM_VIDEO_MODEL", raising=False)


def test_grok_defaults_and_i2v_only(keys, tmp_path):
    g = GrokProvider()
    assert g.base_url == "https://relay.example/v1"
    assert g.model == "grok-imagine-video-1.5" and g.requires_start_image
    with pytest.raises(ValueError, match="图生视频"):
        g.generate_video("p", tmp_path / "a.mp4", 5, "9:16", "720p", None)


def test_grok_video_job_polling(keys, tmp_path, monkeypatch):
    img = tmp_path / "f.png"
    img.write_bytes(PNG)
    g = GrokProvider(poll_interval=0)
    states = iter([{"status": "pending"}, {"status": "done", "video": {"url": "https://cdn/v.mp4"}}])
    g.session = FakeSession({("POST", "/videos/generations"): Resp({"request_id": "r1"}),
                             ("GET", "/videos/r1"): lambda kw: Resp(next(states))})
    downloaded = []
    monkeypatch.setattr(g, "_download", lambda url, out: downloaded.append(url) or out)
    g.generate_video("p", tmp_path / "a.mp4", 6, "9:16", "720p", img)
    body = g.session.calls[0][2]["json"]
    assert body["model"] == "grok-imagine-video-1.5" and body["duration"] == 6
    assert body["image"]["url"].startswith("data:image/png;base64,")
    assert downloaded == ["https://cdn/v.mp4"]


def test_openai_image_via_responses(keys, tmp_path):
    o = OpenAIImageProvider()
    o.session = FakeSession({("POST", "/responses"): Resp({"output": [
        {"type": "reasoning"}, {"type": "image_generation_call", "result": base64.b64encode(PNG).decode()}]})})
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    out = o.generate_image("猫", tmp_path / "k.png", "9:16", [ref])
    assert out.read_bytes() == PNG
    body = o.session.calls[0][2]["json"]
    assert body["tools"][0] == {"type": "image_generation", "size": "864x1536", "quality": "high"}
    assert body["input"][0]["content"][1]["type"] == "input_image"


def test_tripo_image_to_model(keys, tmp_path, monkeypatch):
    t = TripoClient(poll_interval=0)
    states = iter([{"status": "running", "progress": 50},
                   {"status": "success", "output": {"pbr_model": "https://cdn/m.glb"}}])
    t.session = FakeSession({
        ("POST", "/upload"): Resp({"code": 0, "data": {"image_token": "tok"}}),
        ("POST", "/task"): Resp({"code": 0, "data": {"task_id": "t1"}}),
        ("GET", "/task/t1"): lambda kw: Resp({"code": 0, "data": next(states)}),
    })
    got = []
    monkeypatch.setattr(t, "_download_model", lambda task, out: got.append(task["output"]["pbr_model"]) or out)
    img = tmp_path / "c.png"
    img.write_bytes(PNG)
    t.image_to_model(img, tmp_path / "c.glb", log=lambda _: None)
    assert t.session.calls[1][2]["json"] == {"type": "image_to_model", "file": {"type": "png", "file_token": "tok"}}
    assert got == ["https://cdn/m.glb"]


def test_tripo_error_code(keys):
    t = TripoClient()
    t.session = FakeSession({("GET", "/user/balance"): Resp({"code": 1002, "message": "bad key"})})
    with pytest.raises(RuntimeError, match="Tripo"):
        t.balance()


def test_combined_mock_provider():
    p = get_provider("mock")
    assert p.name == "mock" and p.max_clip_seconds == 15
