# Grok Imagine（xAI）使用说明

> 接口字段根据公开资料整理，**首次接入请对照 https://docs.x.ai 核对**。字段拼装集中在
> `videomaker/providers/grok.py` 的 `_video_body` / `_image_body`，有出入时只需改这两处。

## 接口
- 视频：`POST https://api.x.ai/v1/videos/generations` 返回 `request_id`，再轮询 `GET /v1/videos/{request_id}`。
  结果 URL **有时效**，工具会在拿到后立即下载。
- 图像：`POST https://api.x.ai/v1/images/generations`。
- 认证：`Authorization: Bearer $XAI_API_KEY`。

## 模型（通过 `VM_VIDEO_MODEL` 切换）
| 模型 | 能力 | 备注 |
| --- | --- | --- |
| `grok-imagine-video` | 文生视频 + 图生视频 | 默认 |
| `grok-imagine-video-1.5` | **仅图生视频**，带同步音频 | 必须提供首帧，不能用 `start_frame: none` |

限制：单段 1–15 秒，480p / 720p。价格以官方页面为准。

## 提示词写法
工具会自动按"画面 / 角色 / 场景 / 镜头 / 光线 / 氛围 / 风格 / 避免"的结构拼装，作者只需写好各字段：
- **画面（action）**：主语 + 具体动作 + 结果。例："橘猫从台阶跳下，落进水洼溅起水花"。
- **镜头（camera）**：景别 + 运动 + 速度。例："中景，固定机位"或"特写，缓慢环绕 90 度"。
- **图生视频时**，提示词重点写"接下来发生什么"，首帧里已有的内容不必再详细描述。
- 避免抽象形容词堆砌（"超级震撼、史诗级"），多写可以被看见的细节。
- 有台词时写进 `dialogue`；1.5 模型会尝试生成对应声音。

## 经验记录
（发现有效技巧请追加到这里，注明日期与案例）
