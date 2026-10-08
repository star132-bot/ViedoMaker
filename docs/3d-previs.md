# 3D 预演（previs）：用 Blender 稳定构图与动作

纯文字描述很难精确控制站位、机位和透视。先在 3D 里粗略摆好场景，渲染一张图作为视频的**首帧**，模型就会在这个构图上生成动作。

## 什么时候用
- 多个角色有明确的空间关系（谁在左、谁在右、距离多远）
- 同一场景要从多个机位拍摄，并保持空间一致（正反打）
- 需要精确的镜头焦段、俯仰角度或运镜起点
- 文生图反复抽卡都得不到想要的构图

## 流程
0. 生成角色或道具的 3D 模型（Tripo3D）。推荐从角色设定图生成，外观与视频一致：
   ```bash
   vm image "小橘的全身正面设定图，纯白背景，T 字站姿" --out projects/<名字>/assets/cat_ref.png
   vm model3d --image projects/<名字>/assets/cat_ref.png --out projects/<名字>/assets/3d/cat.glb
   vm model3d --prompt "深夜的街角便利店门面，低多边形" --out projects/<名字>/assets/3d/store.glb
   ```
   在 Blender 中用 File → Import → glTF 2.0 导入 `.glb`。
   模型存放在 `tripo-data.*.tripo3d.com`，该域名需要在网络中放行。如果生成成功但下载失败，
   用 `vm model3d --task <任务ID> --out ...` 重新下载，不会再次扣费。实测从图片生成一个模型消耗 30 点，得到约 11MB 的 GLB（约 14 万顶点，带 PBR 材质）。
1. 在 Blender 中用上面生成的模型、简单几何体或免费素材（Mixamo 人物、Poly Haven 场景）搭场景，为每个镜头建一个摄像机，命名为镜头 id（如 `s03`）。
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
