"""把镜头拆成模型能一次生成的"段"（segment）。

模型单次最多生成 max_seconds 秒。超过上限的镜头会被均分成多段，
第 2 段起首帧强制使用上一段的尾帧（chain），从而在画面上无缝衔接。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schema import Project, Shot


@dataclass(frozen=True)
class Segment:
    key: str  # 例："s03" 或 "s03.2"
    shot: Shot
    part: int  # 从 1 开始
    parts: int
    duration: int
    start_frame: str  # chain / keyframe / file / none

    @property
    def is_continuation(self) -> bool:
        return self.part > 1


def split_duration(total: float, max_seconds: int, min_seconds: int = 1) -> list[int]:
    """把时长均分成不超过 max_seconds 的整数秒段落。"""
    n = max(1, math.ceil(total / max_seconds))
    total_int = max(min_seconds * n, round(total))
    base, rem = divmod(total_int, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def plan_segments(project: Project, max_seconds: int) -> list[Segment]:
    segments: list[Segment] = []
    for idx, shot in enumerate(project.shots):
        durations = split_duration(shot.duration, max_seconds)
        for part, dur in enumerate(durations, start=1):
            if part > 1:
                start = "chain"
            elif idx == 0 and shot.start_frame == "chain":
                # 第一个镜头没有"上一段"，退化为生成关键帧
                start = "keyframe"
            else:
                start = shot.start_frame
            key = shot.id if len(durations) == 1 else f"{shot.id}.{part}"
            segments.append(Segment(key, shot, part, len(durations), dur, start))
    return segments
