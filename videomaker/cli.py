"""命令行入口：vm <命令> <项目目录>"""

from __future__ import annotations

import os
from pathlib import Path

import click

from . import pipeline
from .lint import lint
from .plan import plan_segments
from .prompt import keyframe_prompt, video_prompt
from .providers import IMAGE, VIDEO, get_image_provider, get_provider
from .schema import load_project


def _ids(value: str | None) -> set[str]:
    return {x.strip() for x in value.split(",") if x.strip()} if value else set()


def load_dotenv(path: Path = Path(".env")) -> None:
    """读取 .env（不覆盖已存在的环境变量）。支持 `KEY=value` 和 `export KEY=value`。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


video_opt = click.option("--provider", default="grok", show_default=True, type=click.Choice(VIDEO),
                         help="视频模型；mock 为本地模拟")
image_opt = click.option("--image-provider", type=click.Choice(IMAGE),
                         help="图像模型（关键帧/设定图），默认 grok→openai、mock→mock")


@click.group()
def main() -> None:
    """AI 视频制作工具链。"""
    load_dotenv()


@main.command()
@click.argument("project_dir")
def check(project_dir: str) -> None:
    """校验 project.yaml 并给出质量建议。"""
    p = load_project(project_dir)
    segs = plan_segments(p, 15)
    i2v_only = "1.5" in os.environ.get("VM_VIDEO_MODEL", "grok-imagine-video-1.5")
    click.echo(f"✓ {p.title}：{len(p.shots)} 个镜头 → {len(segs)} 段，总时长 {p.total_duration:.0f}s")
    for w in lint(p, requires_start_image=i2v_only):
        click.echo(f"  ⚠ {w}")


@main.command()
@click.argument("project_dir")
@click.option("--max-seconds", default=15, show_default=True)
def prompts(project_dir: str, max_seconds: int) -> None:
    """打印每一段的最终提示词（生成前人工/agent 审阅用）。"""
    p = load_project(project_dir)
    for seg in plan_segments(p, max_seconds):
        click.echo(f"===== {seg.key}  {seg.duration}s  首帧={seg.start_frame} =====")
        if seg.start_frame == "keyframe":
            click.echo("[关键帧提示词]\n" + keyframe_prompt(p, seg.shot) + "\n[视频提示词]")
        click.echo(video_prompt(p, seg) + "\n")


@main.command()
@click.argument("project_dir")
@video_opt
@image_opt
@click.option("--only", help="只生成这些镜头/段落，逗号分隔，如 s02,s03.2")
@click.option("--retake", help="强制重拍这些镜头/段落（旧版本移到 output/takes/）")
def render(project_dir: str, provider: str, image_provider: str | None,
           only: str | None, retake: str | None) -> None:
    """生成视频片段（断点续跑：已是最新的段落会跳过）。"""
    p = load_project(project_dir)
    pipeline.render(p, get_provider(provider, image_provider), _ids(only), _ids(retake), log=click.echo)


@main.command()
@click.argument("project_dir")
def assemble(project_dir: str) -> None:
    """拼接成片：统一规格 + 转场 + 音乐 + 字幕 + 发布元数据。"""
    pipeline.assemble(load_project(project_dir), log=click.echo)


@main.command()
@click.argument("project_dir")
@video_opt
@image_opt
def run(project_dir: str, provider: str, image_provider: str | None) -> None:
    """check → render → assemble 一条龙。"""
    p = load_project(project_dir)
    prov = get_provider(provider, image_provider)
    for w in lint(p, prov.max_clip_seconds, getattr(prov, "requires_start_image", False)):
        click.echo(f"  ⚠ {w}")
    pipeline.render(p, prov, log=click.echo)
    pipeline.assemble(p, prov.max_clip_seconds, log=click.echo)


@main.command()
@click.argument("prompt")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="输出图片路径")
@click.option("--aspect", default="9:16", show_default=True)
@click.option("--ref", "refs", multiple=True, type=click.Path(path_type=Path), help="参考图，可多次")
@click.option("--image-provider", default="openai", show_default=True, type=click.Choice(IMAGE))
def image(prompt: str, out: Path, aspect: str, refs: tuple[Path, ...], image_provider: str) -> None:
    """单独生成一张图（角色设定图、场景母版、关键帧草稿）。"""
    get_image_provider(image_provider).generate_image(prompt, out, aspect, list(refs))
    click.echo(f"[图像] {out}")


@main.command()
@click.option("--prompt", help="文字生成 3D 模型")
@click.option("--image", "image_path", type=click.Path(exists=True, path_type=Path), help="图片生成 3D 模型")
@click.option("--task", "task_id", help="重新下载已完成任务的模型（不扣费）")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="输出 .glb 路径")
def model3d(prompt: str | None, image_path: Path | None, task_id: str | None, out: Path) -> None:
    """用 Tripo3D 生成 3D 模型（GLB），供 Blender 预演使用。"""
    from .model3d import TripoClient

    if sum(map(bool, (prompt, image_path, task_id))) != 1:
        raise click.UsageError("--prompt、--image、--task 三选一")
    client = TripoClient()
    if task_id:
        path = client.fetch(task_id, out, log=click.echo)
    elif image_path:
        path = client.image_to_model(image_path, out, log=click.echo)
    else:
        path = client.text_to_model(prompt, out, log=click.echo)
    click.echo(f"[3D] {path}")


@main.command()
def ping() -> None:
    """检查各模型服务的连通性和密钥（不产生生成费用）。"""
    import requests

    checks = [
        ("Grok 视频", os.environ.get("GROK_MODELS_BASE_URL") or os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1"),
         "XAI_API_KEY", "/models"),
        ("OpenAI 图像", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), "OPENAI_API_KEY", "/models"),
        ("Tripo3D", os.environ.get("TRIPO_BASE_URL", "https://api.tripo3d.ai/v2/openapi"), "TRIPO_API_KEY",
         "/user/balance"),
    ]
    for name, base, key_env, path in checks:
        key = os.environ.get(key_env)
        if not key:
            click.echo(f"✗ {name}: 未设置 {key_env}")
            continue
        try:
            r = requests.get(base.rstrip("/") + path, headers={"Authorization": f"Bearer {key}"}, timeout=30)
            ok = r.status_code < 400
            detail = r.text[:300].replace("\n", " ")
            click.echo(f"{'✓' if ok else '✗'} {name}: HTTP {r.status_code}  {detail}")
        except requests.RequestException as e:
            click.echo(f"✗ {name}: 无法连接 {base}（{type(e).__name__}: {e}）")


if __name__ == "__main__":
    main()
