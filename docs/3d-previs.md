# 3D 预演（previs）：用 Blender 稳定构图与动作

纯文字描述很难精确控制站位、机位和透视。先在 3D 里粗略摆好场景，渲染一张图作为视频的**首帧**，模型就会在这个构图上生成动作。

## 什么时候用
- 多个角色有明确的空间关系（谁在左、谁在右、距离多远）
- 同一场景要从多个机位拍摄，并保持空间一致（正反打）
- 需要精确的镜头焦段、俯仰角度或运镜起点
- 文生图反复抽卡都得不到想要的构图

## 流程
1. 在 Blender 中用简单几何体或免费模型（Mixamo 人物、Poly Haven 场景）搭场景，为每个镜头建一个摄像机，命名为镜头 id（如 `s03`）。
2. 渲染首帧：
   ```bash
   blender -b scene.blend -P tools/blender/render_layout.py -- \
       --camera s03 --out projects/<名字>/assets/previs/s03.png --aspect 9:16
   ```
3. 粗模渲染图风格与成片不同。可以选择：
   - **直接用作首帧**：在 `extra_prompt` 写"将画面渲染为<风格>，保持构图与人物位置"。
   - **先转风格再用**（推荐）：用图像模型以渲染图为参考生成风格化关键帧，再作为首帧。
4. 在 project.yaml 中设置：
   ```yaml
   start_frame: file
   start_image: assets/previs/s03.png
   ```

## 进阶（待实现）
- 渲染深度图或姿态图，用于支持 ControlNet 类控制的模型
- 渲染摄像机动画的首尾帧，用于支持首尾帧控制的模型
