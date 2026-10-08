"""质量检查：在花钱生成之前，找出会导致"效果差"的设定问题。

返回的是建议（warning），不阻止生成；格式错误由 schema 校验负责。
"""

from __future__ import annotations

from .plan import plan_segments
from .prompt import reference_images, video_prompt
from .schema import Project

MAX_PROMPT_CHARS = 1800
CHARS_PER_SECOND = 5  # 中文台词语速上限（字/秒）


def lint(project: Project, max_seconds: int = 15) -> list[str]:
    w: list[str] = []
    s = project.style
    if not s.look:
        w.append("style.look 为空：没有统一画风，镜头之间容易风格漂移")
    if not s.avoid:
        w.append("style.avoid 为空：建议列出不想要的元素（如：文字水印、畸形手指、画面闪烁）")
    for c in project.characters:
        if len(c.description) < 15:
            w.append(f"角色 {c.id} 外观描述过短：写清年龄、发型、五官、体型、标志性特征，才能保持一致")
        if not c.reference_images:
            w.append(f"角色 {c.id} 没有设定图：建议先生成/绘制三视图放进 assets/ 并作为参考")
    for path in {r for shot in project.shots for r in reference_images(project, shot)}:
        if not project.path(path).exists():
            w.append(f"参考图不存在: {path}")

    prev = None
    for shot in project.shots:
        if not shot.camera and not s.camera:
            w.append(f"镜头 {shot.id} 没有写镜头语言（景别 + 运镜），模型会随意发挥")
        if shot.start_frame == "chain" and prev and prev.location != shot.location:
            w.append(f"镜头 {shot.id} 换了场景却用尾帧接力（chain），建议改为 keyframe 或 file")
        elif shot.start_frame == "chain" and prev and shot.camera and prev.camera and shot.camera != prev.camera:
            w.append(f"镜头 {shot.id} 换了景别/机位却用尾帧接力：画面会从上个镜头的构图开始，"
                     "切镜请用 keyframe 或 file；chain 适合同一机位的连续动作")
        if shot.start_frame == "file" and shot.start_image and not project.path(shot.start_image).exists():
            w.append(f"镜头 {shot.id} 的首帧图片不存在: {shot.start_image}")
        if shot.dialogue and len(shot.dialogue) > shot.duration * CHARS_PER_SECOND:
            w.append(f"镜头 {shot.id} 台词 {len(shot.dialogue)} 字，{shot.duration}s 说不完")
        if shot.duration > max_seconds * 2:
            w.append(f"镜头 {shot.id} 长达 {shot.duration}s，需接力 {int(shot.duration // max_seconds) + 1} 段，"
                     "画面会逐段劣化，建议拆成多个不同景别的镜头")
        prev = shot

    for seg in plan_segments(project, max_seconds):
        n = len(video_prompt(project, seg))
        if n > MAX_PROMPT_CHARS:
            w.append(f"段落 {seg.key} 提示词 {n} 字，过长会被忽略重点，建议精简")
    return w
