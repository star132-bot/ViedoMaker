"""把项目设定 + 镜头组装成最终提示词。

原则：
- 角色外观、场景、风格每次都"原样重复"，不让模型自由发挥 → 一致性。
- 结构固定：主体/动作 → 场景 → 镜头 → 光线 → 氛围 → 风格 → 避免项。
- 接力段落强调"延续首帧画面"，避免跳变。
"""

from __future__ import annotations

from .plan import Segment
from .schema import Project, Shot


def _characters_block(project: Project, shot: Shot) -> str:
    parts = []
    for cid in shot.characters:
        c = project.character(cid)
        desc = c.description
        if c.wardrobe:
            desc += f"，身穿{c.wardrobe}"
        parts.append(f"{c.name or c.id}：{desc}")
    return "；".join(parts)


def _join(lines: list[tuple[str, str]]) -> str:
    return "\n".join(f"{k}：{v}" for k, v in lines if v and v.strip())


def video_prompt(project: Project, seg: Segment) -> str:
    shot = seg.shot
    style = project.style
    action = shot.action
    if seg.is_continuation:
        action = shot.continuation_prompt or shot.action
        action = f"紧接首帧画面继续：{action}（保持人物、服装、场景、光线与首帧完全一致，不要切镜）"
    elif seg.start_frame == "chain":
        action = f"{action}（与首帧画面自然衔接）"

    lines = [
        ("画面", action),
        ("角色", _characters_block(project, shot)),
        ("场景", project.location(shot.location).description if shot.location else ""),
        ("镜头", shot.camera or style.camera),
        ("光线", shot.lighting or style.lighting),
        ("氛围", shot.mood),
        ("风格", "，".join(x for x in (style.look, style.palette) if x)),
        ("台词", f"“{shot.dialogue}”" if shot.dialogue else ""),
        ("补充", shot.extra_prompt),
        ("避免", "、".join(style.avoid)),
    ]
    return _join(lines)


def keyframe_prompt(project: Project, shot: Shot) -> str:
    """生成镜头首帧（静态图）的提示词：描述"定格的那一瞬间"，不写运镜。"""
    style = project.style
    lines = [
        ("画面", shot.keyframe_prompt or shot.action),
        ("角色", _characters_block(project, shot)),
        ("场景", project.location(shot.location).description if shot.location else ""),
        ("构图", shot.camera),
        ("光线", shot.lighting or style.lighting),
        ("氛围", shot.mood),
        ("风格", "，".join(x for x in (style.look, style.palette) if x)),
        ("画幅", f"{project.output.aspect_ratio}，画面铺满整个画幅，无黑边、无边框"),
        ("避免", "、".join(style.avoid)),
    ]
    return _join(lines)


def reference_images(project: Project, shot: Shot) -> list[str]:
    """该镜头可用的参考图（角色设定图 + 场景图），相对项目目录。"""
    refs: list[str] = []
    for cid in shot.characters:
        refs += project.character(cid).reference_images
    if shot.location:
        refs += project.location(shot.location).reference_images
    return refs
