# Grok Imagine（xAI）使用说明

> 接口字段根据公开资料整理，**首次接入请对照 https://docs.x.ai 核对**。字段拼装集中在
> `videomaker/providers/grok.py` 的 `_video_body` / `_image_body`，有出入时只需改这两处。

## 配置
```bash
XAI_API_KEY=...
GROK_MODELS_BASE_URL=https://api.x.ai/v1   # 使用中转服务时改成中转地址
VM_VIDEO_MODEL=grok-imagine-video-1.5      # 默认
```

## 接口
- 视频：`POST https://api.x.ai/v1/videos/generations` 返回 `request_id`，再轮询 `GET /v1/videos/{request_id}`。
  结果 URL **有时效**，工具会在拿到后立即下载。
- 图像：`POST https://api.x.ai/v1/images/generations`。
- 认证：`Authorization: Bearer $XAI_API_KEY`。

## 模型（通过 `VM_VIDEO_MODEL` 切换）
| 模型 | 能力 | 备注 |
| --- | --- | --- |
| `grok-imagine-video-1.5` | **仅图生视频**，带同步音频 | 默认；必须提供首帧，不能用 `start_frame: none` |
| `grok-imagine-video` | 文生视频 + 图生视频 | |

限制：单段 1–15 秒，480p / 720p。价格以官方页面为准。

## 提示词写法
工具会自动按"画面 / 角色 / 场景 / 镜头 / 光线 / 氛围 / 风格 / 避免"的结构拼装，作者只需写好各字段：
- **画面（action）**：主语 + 具体动作 + 结果。例："橘猫从台阶跳下，落进水洼溅起水花"。
- **镜头（camera）**：景别 + 运动 + 速度。例："中景，固定机位"或"特写，缓慢环绕 90 度"。
- **图生视频时**，提示词重点写"接下来发生什么"，首帧里已有的内容不必再详细描述。
- 避免抽象形容词堆砌（"超级震撼、史诗级"），多写可以被看见的细节。
- 有台词时写进 `dialogue`；1.5 模型会尝试生成对应声音。

## 实测记录（2026-10-08，中转服务 194834.xyz）
- `GET /models` 可用的相关模型：`grok-imagine-video-1.5`、`grok-imagine-image-2.0`、`grok-imagine-image-quality`。
- `POST /videos/generations` 的请求字段：`model / prompt / duration / aspect_ratio / resolution / image.url(data URI)`，返回 `{"request_id": ...}`。
- 轮询 `GET /videos/{id}`：先返回 `{"status":"pending","progress":1}`，完成后返回
  `{"status":"done","video":{"url":"/v1/videos/{id}/content","duration":5},"usage":{"cost_in_usd_ticks":...}}`。
  **视频地址是相对路径，下载时需要带鉴权头**（工具已处理）。
- 5 秒 480p 的视频约 11 秒生成完成；`cost_in_usd_ticks` 为 4.1e9，约合 0.41 美元（按 1e10 tick = 1 美元换算）。
- 16:9 画幅下 480p 实际输出 736×400（约 1.84:1），拼接时会放大并居中裁切到标准 16:9，不留黑边。
- gpt-image-2.5 支持 1536×864（标准 16:9），关键帧按这个尺寸生成。
- **不要在提示词里写"宽银幕"**：图像模型会把上下黑条画进首帧（实测上下各 105px），视频也会继承黑条。关键帧提示词已经固定带上"画面铺满整个画幅，无黑边"，`vm check` 也会提示这类用词。
- 1:1 画幅下 480p 实际输出 544×544、24fps，**自带音轨**，另有一条封面图视频流（抽帧时需取 `0:v:0`）。
- 角色一致性：用设定图作为首帧时，5 秒内毛色、白爪和耳朵缺口都保持稳定。

## 网络（云环境）
需要放行：
- `194834.xyz`：Grok 视频
- `www.bb-api.com` 和 `img2.lsyzzzz.com`：gpt-image-2.5。中转服务经常只返回图床地址，不返回 base64，所以图床域名也要放行
- `api.tripo3d.ai` 和 `tripo-data.rg1.data.tripo3d.com`：Tripo 的 API 和模型下载

## 分工
- **Grok 只用于生成视频。**
- **图像（关键帧、设定图）只用 gpt-image-2.5**（`vm image`、`--image-provider openai`）。带参考图时走 `/images/edits`，实测中转服务会把它映射到 gpt-image-2。

## 端到端实测（2026-10-08）
2 个镜头、3 段、21 秒、480p 竖屏（这次因为图床域名未放行，关键帧临时用 Grok 图像模型生成）：关键帧 → 图生视频 → 尾帧接力 → 拼接 → 字幕，全部跑通。
- 尾帧接力的衔接处（同一镜头的两段之间）几乎看不出接缝。
- 不同镜头的关键帧如果不带参考图，猫的特征（白胸口等）会不一致。**角色必须配设定图**。
- 场景里写"便利店"时，模型会画出类似真实品牌的招牌。在 `avoid` 里加上"品牌标志、可读的招牌文字"。
- 第二次实测：关键帧改用 gpt-image-2.5，并带上角色设定图（走 `/images/edits`）。两个镜头里猫的体型、白胸口和白爪保持一致，也没有再出现品牌招牌。**结论：设定图加上 avoid 约束是保持一致性的关键。**
- 中转服务 `www.bb-api.com` 偶尔会断开连接，图像请求已加入重试（2s、4s、8s）。

## 经验记录
（发现有效技巧请追加到这里，注明日期与案例）
