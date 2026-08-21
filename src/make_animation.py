"""将 舔毛.mp4 逐帧处理成与静止猫完全一致的透明动画帧。

方法（保证色调与静止图一致）：
1. 逐帧读视频，用 rembg(u2net) AI 抠图——与 cat.png 同源抠图，色彩天然一致
2. 按抠图主体 bbox 裁剪，缩放到 cat.png 尺寸，使大小位置与静止图一致

输出: _anim_frames/f000.png ... （BGRA PNG，尺寸=cat.png 尺寸）
"""
import os
import numpy as np
from PIL import Image
import cv2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("U2NET_HOME", os.path.join(ROOT_DIR, ".rembg", "models"))
from rembg import remove, new_session

VIDEO = os.path.join(ROOT_DIR, "source_media", "舔毛.mp4")
CAT_IMG = os.path.join(ROOT_DIR, "assets", "cat.png")
OUT_DIR = os.path.join(ROOT_DIR, "assets", "_anim_frames")
os.makedirs(OUT_DIR, exist_ok=True)

MODEL_PATH = os.path.join(ROOT_DIR, ".rembg", "models", "u2net", "u2net.onnx")
session = new_session("u2net_custom", model_path=MODEL_PATH)

# 目标尺寸 = cat.png 尺寸
cat = cv2.imread(CAT_IMG, cv2.IMREAD_UNCHANGED)
TARGET_SIZE = (cat.shape[1], cat.shape[0])  # (w, h) = (165, 220)
print(f"目标尺寸: {TARGET_SIZE}")


def process_frame(frame_bgr):
    """返回 BGRA uint8（尺寸=TARGET_SIZE）。全程用原生 BGR，不做 RGB 转换。"""
    # rembg 需要 RGB PIL 输入
    pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    out = np.array(remove(pil, session=session))  # RGBA uint8, 960x960

    alpha = out[:, :, 3]
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return None
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()

    # RGBA -> BGRA（统一用 OpenCV 原生顺序）
    bgra = cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA)
    crop = bgra[y0:y1 + 1, x0:x1 + 1]

    # 缩放到目标尺寸（主体撑满）
    resized = cv2.resize(crop, TARGET_SIZE, interpolation=cv2.INTER_AREA)
    return resized


cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    raise SystemExit("无法打开视频")
idx = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    bgra = process_frame(frame)
    if bgra is not None:
        out_path = os.path.join(OUT_DIR, f"f{idx:03d}.png")
        cv2.imwrite(out_path, bgra)
    idx += 1
cap.release()
print(f"完成，共 {idx} 帧 -> {OUT_DIR}，尺寸 {TARGET_SIZE}")
