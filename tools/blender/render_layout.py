"""在 Blender 中渲染指定摄像机的预演首帧。

用法：
  blender -b scene.blend -P tools/blender/render_layout.py -- --camera s03 --out out.png [--aspect 9:16] [--short 720]
"""

import argparse
import sys

import bpy  # noqa: 只在 Blender 内可用

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--camera", required=True, help="摄像机对象名（建议与镜头 id 一致）")
ap.add_argument("--out", required=True)
ap.add_argument("--aspect", default="9:16")
ap.add_argument("--short", type=int, default=720, help="短边像素")
ap.add_argument("--frame", type=int, default=None, help="渲染哪一帧（默认当前帧）")
args = ap.parse_args(argv)

scene = bpy.context.scene
cam = bpy.data.objects.get(args.camera)
if cam is None or cam.type != "CAMERA":
    sys.exit(f"找不到摄像机: {args.camera}")
scene.camera = cam

a, b = (int(x) for x in args.aspect.split(":"))
if a >= b:
    w, h = args.short * a // b, args.short
else:
    w, h = args.short, args.short * b // a
scene.render.resolution_x, scene.render.resolution_y = w // 2 * 2, h // 2 * 2
scene.render.resolution_percentage = 100
if args.frame is not None:
    scene.frame_set(args.frame)
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = args.out
bpy.ops.render.render(write_still=True)
print(f"已渲染 {args.camera} → {args.out}")
