# ViedoMaker

用 AI 视频模型（目前接入 **Grok Imagine**）制作高质量视频的工具链，人和 agent 都能用。

```
创意 → project.yaml（风格/角色/场景/分镜）→ 关键帧 → 分段生成（尾帧接力突破 15 秒）
     → 质检/重拍 → 拼接 + 转场 + 字幕 + 音乐 → 发布素材
```

## 快速开始

```bash
pip install -e '.[dev]'                                  # 需要 Python ≥3.10 和 ffmpeg
vm check projects/example-rain-cat                       # 校验示例项目
vm run   projects/example-rain-cat --provider mock       # 本地模拟全流程，不花钱
export XAI_API_KEY=xai-...
vm run   projects/example-rain-cat                       # 用 Grok 真实生成
```

成片位于 `projects/example-rain-cat/output/rain-cat.mp4`。

## 新建视频

复制 `projects/example-rain-cat/`，修改 `project.yaml`。字段说明见 [docs/project-format.md](docs/project-format.md)。

## 给 agent

先读 [AGENTS.md](AGENTS.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `videomaker/` | 工具链源码（schema、拆段、提示词组装、provider、ffmpeg、流程、CLI） |
| `projects/` | 每个视频一个目录 |
| `docs/` | 质量要素、模型技巧、3D 预演 |
| `tools/blender/` | 3D 预演渲染脚本 |
| `tests/` | 测试（用 mock provider，无需 API） |
