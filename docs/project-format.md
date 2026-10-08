# project.yaml 字段说明

完整示例见 `projects/example-rain-cat/project.yaml`。所有路径都相对于项目目录。格式定义见 `videomaker/schema.py`。

```yaml
id: my-video                 # 用作输出文件名
title: 标题
logline: 一句话故事

output:
  aspect_ratio: "16:9"       # 默认横屏；16:9 | 9:16 | 1:1 | 4:3 | 3:4
  resolution: 720p           # 480p | 720p
  fps: 24

style:                       # 全片统一，每段提示词都会带上
  look: 画风/质感
  palette: 色调
  lighting: 默认光线
  camera: 默认镜头语言
  avoid: [不想要的元素]

characters:
  - id: hero
    name: 显示名
    description: 锁定外观（越具体越稳定）
    wardrobe: 服装
    reference_images: [assets/hero_ref.png]

locations:
  - id: street
    description: 场景描述
    reference_images: []

shots:
  - id: s01                  # 唯一
    duration: 8              # 秒；超过模型上限会自动拆段接力
    action: 画面中发生什么
    characters: [hero]
    location: street
    camera: 景别 + 运镜
    lighting: 覆盖默认光线（可选）
    mood: 氛围
    dialogue: 台词（生成字幕）
    extra_prompt: 额外提示词
    start_frame: keyframe    # keyframe | chain | file | none
    keyframe_prompt: 首帧静态画面描述（可选）
    start_image: assets/previs/s01.png   # start_frame=file 时必填
    continuation_prompt: 拆段后后续段落的动作（可选）
    transition: cut          # cut | fade，与下一个镜头之间的转场

audio:
  music: assets/bgm.mp3      # 可选
  music_volume: 0.3
  keep_clip_audio: true
  burn_subtitles: false

publish:
  - platform: douyin
    title: 发布标题
    description: 简介
    tags: [标签]
```

## 输出目录
```
output/
  keyframes/<shot>.png       关键帧
  clips/<segment>.mp4        模型原始片段
  frames/<segment>_last.png  每段尾帧（接力用，也用于质检）
  takes/                     重拍前的旧版本
  normalized/                统一规格后的片段
  <id>.mp4 / <id>.srt        成片与字幕
  publish/<platform>.json    发布元数据
  manifest.json              生成状态（提示词、指纹、时间）
```
