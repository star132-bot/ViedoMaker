# AGENTS.md — 给所有制作视频的 agent

这个仓库只做一件事：**用 AI 视频模型制作优秀的视频**。任何 agent（Claude、Codex、Cursor、自建 agent……）都按本文流程工作。

## 核心概念

- **项目** = `projects/<名字>/project.yaml`：风格、角色、场景、镜头列表。视频是"写"在这个文件里的。
- **镜头（shot）** 可以任意长；超过模型单次上限（Grok 为 15 秒）时自动拆成多"段"，用**尾帧接力**衔接。
- **首帧来源**（`start_frame`）决定画面稳定性：
  - `keyframe`：先生成一张静态首帧，再图生视频。**新场景、新机位一律用它。**
  - `chain`：用上一段的最后一帧。只用于**同一机位的连续动作**。
  - `file`：用现成图片：3D 预演渲染图、手绘分镜、实拍参考。需要精确构图/动作时用它。
  - `none`：纯文生视频，最不可控，尽量少用。
- 所有产物在 `projects/<名字>/output/`（不进 git），状态在 `output/manifest.json`。

## 标准流程

```bash
pip install -e '.[dev]'
cp .env.example .env                         # 填入密钥（.env 不会提交）；vm 自动读取
vm ping                                      # 0. 检查三个服务的连通性和密钥

vm check   projects/<名字>                   # 1. 校验 + 质量建议，先把 ⚠ 处理掉
vm prompts projects/<名字>                   # 2. 审阅每段最终提示词
vm render  projects/<名字> --provider mock   # 3. 本地模拟跑通流程（不花钱）
vm render  projects/<名字>                   # 4. 真实生成（断点续跑，已完成的会跳过）
vm render  projects/<名字> --retake s03      # 5. 不满意就重拍某个镜头/段落
vm assemble projects/<名字>                  # 6. 拼接成片 + 字幕 + 音乐 + 发布元数据
```

## 用到的模型

| 用途 | 服务 | 命令 / 配置 |
| --- | --- | --- |
| 视频 | Grok Imagine Video 1.5（仅图生视频） | `vm render`，`XAI_API_KEY` + `GROK_MODELS_BASE_URL` |
| 图像（关键帧、设定图） | gpt-image-2.5（OpenAI 兼容 /images 接口）。Grok 只用于视频，不用来生图 | `vm image`，`OPENAI_API_KEY` + `OPENAI_BASE_URL` |
| 3D（预演用模型） | Tripo3D | `vm model3d`，`TRIPO_API_KEY` |

因为 Grok 1.5 只做图生视频，**每段都必须有首帧**：第一个镜头和新机位用 `keyframe`（由图像模型生成），或者用 `file`。

**画幅默认横屏 16:9。** 新项目一律用 `aspect_ratio: "16:9"`，关键帧、设定图、3D 预演渲染也用横构图；只有用户明确要求时才做竖屏。

**密钥只放在 `.env` 或环境变量里，绝不写进 project.yaml、代码或提交记录。**

## 规则

1. **先计划，后花钱。** 生成前必须 `vm check` 无严重问题，并读过 `vm prompts` 的输出。
2. **先用 mock 跑通。** 改了 project.yaml 结构后，先 `--provider mock` 跑一遍。
3. **逐个检查片段。** 每生成一段，就看它的尾帧（`output/frames/`）和视频。有变脸、肢体畸形、穿帮、闪烁时，用 `--retake` 重拍，**不要带着坏段落往下接力**，因为后面的段落会继承问题。
4. **一致性靠重复，不靠记忆。** 角色外观只写在 `characters[].description` 里，镜头中不要重新描述外貌。
5. **画质与提示词的技巧写进 docs/。** 发现有效的新技巧，就补充到 `docs/quality-elements.md` 或 `docs/grok.md`，让其他 agent 也能用上。
6. **接入新模型** 只需在 `videomaker/providers/` 实现 `VideoProvider`，并在 `providers/__init__.py` 注册。
7. 改代码后运行 `python -m pytest -q`。

## 文档索引

- `docs/quality-elements.md`：制作优秀视频的要素清单（从剧本到发布）
- `docs/grok.md`：Grok Imagine 的接口、限制与提示词写法
- `docs/3d-previs.md`：用 3D 预演（Blender）稳定构图与动作
- `docs/project-format.md`：project.yaml 字段说明
