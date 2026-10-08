"""视频项目的数据格式（project.yaml）。

一个项目 = 风格设定 + 角色 + 场景 + 一组镜头（shot）。
所有 agent 都通过编辑 project.yaml 来"写"视频，再由 pipeline 执行生成。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

AspectRatio = Literal["16:9", "9:16", "1:1", "4:3", "3:4"]
StartFrame = Literal["chain", "keyframe", "file", "none"]
Transition = Literal["cut", "fade"]


class Output(BaseModel):
    aspect_ratio: AspectRatio = "9:16"
    resolution: Literal["480p", "720p"] = "720p"
    fps: int = 24


class Style(BaseModel):
    """全片统一的视觉风格。每个镜头的提示词都会带上它，保证画风不漂移。"""

    look: str = ""  # 例：电影感写实，35mm 胶片颗粒
    palette: str = ""  # 色调
    lighting: str = ""  # 默认光线
    camera: str = ""  # 默认镜头语言
    avoid: list[str] = Field(default_factory=list)  # 不希望出现的元素


class Character(BaseModel):
    """角色设定。description 是"锁定外观"，每次出场都原样带上。"""

    id: str
    name: str = ""
    description: str  # 外貌：年龄、体型、发型、五官、特征
    wardrobe: str = ""  # 服装
    reference_images: list[str] = Field(default_factory=list)  # 角色设定图（三视图等）


class Location(BaseModel):
    id: str
    description: str
    reference_images: list[str] = Field(default_factory=list)


class Shot(BaseModel):
    """一个镜头。duration 可以超过模型单次上限，pipeline 会自动拆段并尾帧接力。"""

    id: str
    duration: float = Field(gt=0)
    action: str  # 画面里发生什么（主体 + 动作）
    characters: list[str] = Field(default_factory=list)
    location: str | None = None
    camera: str = ""  # 景别 + 运镜，例："中景，缓慢推近"
    lighting: str = ""
    mood: str = ""
    dialogue: str = ""  # 台词/字幕文本
    extra_prompt: str = ""  # 额外的自由提示词

    # 首帧来源：
    #   chain    上一段视频的最后一帧（默认，保证连贯）
    #   keyframe 先用图像模型生成首帧（适合新场景的第一个镜头）
    #   file     使用现成图片（如 3D 预演渲染图、手绘分镜、实拍参考）
    #   none     纯文生视频
    start_frame: StartFrame = "chain"
    keyframe_prompt: str = ""  # start_frame=keyframe 时的额外描述
    start_image: str | None = None  # start_frame=file 时的图片路径（相对项目目录）
    transition: Transition = "cut"  # 与下一个镜头之间的转场
    continuation_prompt: str = ""  # 拆段后续段落的动作描述（不填则沿用 action）

    @model_validator(mode="after")
    def _check_start(self) -> "Shot":
        if self.start_frame == "file" and not self.start_image:
            raise ValueError(f"镜头 {self.id}: start_frame=file 时必须填写 start_image")
        return self


class PublishTarget(BaseModel):
    platform: str  # douyin / bilibili / youtube / tiktok / ...
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class Audio(BaseModel):
    music: str | None = None  # 背景音乐文件路径
    music_volume: float = 0.3
    keep_clip_audio: bool = True  # 保留模型生成的原声
    burn_subtitles: bool = False  # 把台词烧录进画面（需要 ffmpeg 支持 libass）


class Project(BaseModel):
    id: str
    title: str
    logline: str = ""  # 一句话故事
    output: Output = Field(default_factory=Output)
    style: Style = Field(default_factory=Style)
    characters: list[Character] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    shots: list[Shot]
    audio: Audio = Field(default_factory=Audio)
    publish: list[PublishTarget] = Field(default_factory=list)

    # 加载时记录项目目录，用于解析相对路径
    root: Path = Field(default=Path("."), exclude=True)

    @field_validator("shots")
    @classmethod
    def _unique_ids(cls, shots: list[Shot]) -> list[Shot]:
        ids = [s.id for s in shots]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"镜头 id 重复: {sorted(dupes)}")
        return shots

    @model_validator(mode="after")
    def _check_refs(self) -> "Project":
        chars = {c.id for c in self.characters}
        locs = {l.id for l in self.locations}
        for s in self.shots:
            for c in s.characters:
                if c not in chars:
                    raise ValueError(f"镜头 {s.id} 引用了未定义的角色: {c}")
            if s.location and s.location not in locs:
                raise ValueError(f"镜头 {s.id} 引用了未定义的场景: {s.location}")
        return self

    def character(self, cid: str) -> Character:
        return next(c for c in self.characters if c.id == cid)

    def location(self, lid: str) -> Location:
        return next(l for l in self.locations if l.id == lid)

    def path(self, rel: str) -> Path:
        return (self.root / rel).resolve()

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.shots)


def load_project(path: str | Path) -> Project:
    """path 可以是项目目录，也可以直接是 project.yaml。"""
    p = Path(path)
    if p.is_dir():
        p = p / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    project = Project.model_validate(data)
    project.root = p.parent.resolve()
    return project
