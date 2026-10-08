"""命令行入口：vm <命令> <项目目录>"""

from __future__ import annotations

import click

from . import pipeline
from .lint import lint
from .plan import plan_segments
from .prompt import keyframe_prompt, video_prompt
from .providers import get_provider
from .schema import load_project


def _ids(value: str | None) -> set[str]:
    return {x.strip() for x in value.split(",") if x.strip()} if value else set()


@click.group()
def main() -> None:
    """AI 视频制作工具链。"""


@main.command()
@click.argument("project_dir")
def check(project_dir: str) -> None:
    """校验 project.yaml 并给出质量建议。"""
    p = load_project(project_dir)
    segs = plan_segments(p, 15)
    click.echo(f"✓ {p.title}：{len(p.shots)} 个镜头 → {len(segs)} 段，总时长 {p.total_duration:.0f}s")
    for w in lint(p):
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
@click.option("--provider", default="grok", show_default=True, help="grok 或 mock（本地测试）")
@click.option("--only", help="只生成这些镜头/段落，逗号分隔，如 s02,s03.2")
@click.option("--retake", help="强制重拍这些镜头/段落（旧版本移到 output/takes/）")
def render(project_dir: str, provider: str, only: str | None, retake: str | None) -> None:
    """生成视频片段（断点续跑：已是最新的段落会跳过）。"""
    p = load_project(project_dir)
    pipeline.render(p, get_provider(provider), _ids(only), _ids(retake), log=click.echo)


@main.command()
@click.argument("project_dir")
def assemble(project_dir: str) -> None:
    """拼接成片：统一规格 + 转场 + 音乐 + 字幕 + 发布元数据。"""
    pipeline.assemble(load_project(project_dir), log=click.echo)


@main.command()
@click.argument("project_dir")
@click.option("--provider", default="grok", show_default=True)
def run(project_dir: str, provider: str) -> None:
    """check → render → assemble 一条龙。"""
    p = load_project(project_dir)
    for w in lint(p):
        click.echo(f"  ⚠ {w}")
    prov = get_provider(provider)
    pipeline.render(p, prov, log=click.echo)
    pipeline.assemble(p, prov.max_clip_seconds, log=click.echo)


if __name__ == "__main__":
    main()
