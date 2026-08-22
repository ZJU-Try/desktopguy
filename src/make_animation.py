"""将 舔毛.mp4 和 walkleft.mp4 逐帧处理成与静止 cat.png 完全一致的透明动画帧。

对齐方法（保证大小、位置、色调与静止图完全相同）：
1. 以 cat.png 为"参考模板"，读取其主体（alpha>10）的包围盒作为基准
2. 逐帧读视频，rembg(u2net) 抠图，得到 RGBA
3. 取本帧主体 bbox，全局统一缩放比例（以第一个姿态帧为基准）
4. 色调匹配到 cat.png
5. 底边对齐 + 水平居中，放置到 cat 尺寸的画布
6. 统一用 PIL 保存 RGBA

输出:
  assets/_tianmao_frames/f000.png ...   舔毛动画 (首帧 f000 复用 cat.png)
  assets/_walkleft_frames/f000.png ...  walkleft 动画（中间帧体型与静止猫同大同底边）
"""
import os
import json
import numpy as np
from PIL import Image
import cv2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("U2NET_HOME", os.path.join(ROOT_DIR, ".rembg", "models"))
from rembg import remove, new_session

CAT_IMG = os.path.join(ROOT_DIR, "assets", "cat.png")

MODEL_PATH = os.path.join(ROOT_DIR, ".rembg", "models", "u2net", "u2net.onnx")
session = new_session("u2net_custom", model_path=MODEL_PATH)


# ---- 加载 cat.png 基准 ----
def _load_cat_ref():
    """加载 cat.png，返回画布尺寸、主体 bbox、色调参考。"""
    cat_rgb = cv2.cvtColor(cv2.imread(CAT_IMG, cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA)
    cat_a = cat_rgb[:, :, 3]
    rec_y, rec_x = np.where(cat_a > 10)
    ref_x0, ref_x1 = int(rec_x.min()), int(rec_x.max())
    ref_y0, ref_y1 = int(rec_y.min()), int(rec_y.max())
    ref_w = ref_x1 - ref_x0 + 1
    ref_h = ref_y1 - ref_y0 + 1
    can_w, can_h = cat_rgb.shape[1], cat_rgb.shape[0]

    cat_mask = cat_rgb[:, :, 3] > 40
    cat_mean = {c: float(cat_rgb[:, :, c][cat_mask].mean()) for c in range(3)}
    cat_std = {c: float(cat_rgb[:, :, c][cat_mask].std()) for c in range(3)}
    return {
        "can_w": can_w, "can_h": can_h,
        "ref_x0": ref_x0, "ref_x1": ref_x1,
        "ref_y0": ref_y0, "ref_y1": ref_y1,
        "ref_h": ref_h,
        "cat_mean": cat_mean, "cat_std": cat_std,
        "cat_rgb": cat_rgb,
    }


def _crop_alpha(out):
    alpha = out[:, :, 3]
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return None
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    return out[y0:y1 + 1, x0:x1 + 1], x0, y0


def _match_tone(rgba, cat_mean, cat_std):
    m = rgba[:, :, 3] > 40
    res = rgba.astype(np.float32)
    for c in range(3):
        vals = rgba[:, :, c][m]
        if vals.size == 0:
            continue
        mean, std = float(vals.mean()), float(vals.std())
        if std < 1e-3:
            std = 1.0
        res[:, :, c] = (rgba[:, :, c].astype(np.float32) - mean) / std * cat_std[c] + cat_mean[c]
    return np.clip(res, 0, 255).astype(np.uint8)


def _process_frame(frame_bgr, scale, ref):
    can_w, can_h = ref["can_w"], ref["can_h"]
    ref_x0, ref_y1 = ref["ref_x0"], ref["ref_y1"]

    pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    out = np.array(remove(pil, session=session))
    res = _crop_alpha(out)
    if res is None:
        return None
    crop, _, _ = res

    nw = max(1, int(round(crop.shape[1] * scale)))
    nh = max(1, int(round(crop.shape[0] * scale)))
    resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
    resized = _match_tone(resized, ref["cat_mean"], ref["cat_std"])

    canvas = np.zeros((can_h, can_w, 4), dtype=np.uint8)
    x = (can_w - nw) // 2
    y = ref_y1 - nh + 1
    x0c, x1c = max(0, x), min(can_w, x + nw)
    y0c, y1c = max(0, y), min(can_h, y + nh)
    rx0, ry0 = x0c - x, y0c - y
    canvas[y0c:y1c, x0c:x1c] = resized[ry0:ry0 + (y1c - y0c), rx0:rx0 + (x1c - x0c)]
    return canvas


def process_video_to_frames(video_path, out_dir, ref, include_cat_first=False):
    """把视频逐帧处理成 RGBA PNG 序列，输出到 out_dir。

    Args:
        video_path: 视频文件路径
        out_dir: 输出目录
        ref: cat 参考字典（来自 _load_cat_ref）
        include_cat_first: 是否用 cat.png 作为首帧 f000（用于舔毛动画，使点击瞬间无缝）
    """
    os.makedirs(out_dir, exist_ok=True)

    if include_cat_first:
        Image.open(CAT_IMG).save(os.path.join(out_dir, "f000.png"))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频: {video_path}")

    # 第一遍：确定全局缩放比例
    gscale = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        out = np.array(remove(pil, session=session))
        res = _crop_alpha(out)
        if res is not None:
            crop, _, _ = res
            gscale = ref["ref_h"] / crop.shape[0]
            print(f"  基准姿态主体高 {crop.shape[0]}px -> 全局缩放 {gscale:.4f}")
            break
    cap.release()
    if gscale is None:
        raise SystemExit(f"无法从视频取到任何有效帧: {video_path}")

    # 第二遍：逐帧处理输出
    cap = cv2.VideoCapture(video_path)
    idx = 1 if include_cat_first else 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        canvas = _process_frame(frame, gscale, ref)
        if canvas is not None:
            out_path = os.path.join(out_dir, f"f{idx:03d}.png")
            Image.fromarray(canvas, "RGBA").save(out_path)
        idx += 1
    cap.release()
    print(f"  完成，共 {idx} 帧 -> {out_dir}")


def process_walk_to_frames(video_path, out_dir, ref, offsets_path, margin=14):
    """walkleft 专用：用更大画布保证完整显示，所有帧缩放到与静止猫同一高度。

    关键：
    - 统一固定缩放比例（不是每帧单独缩放，避免体型渐变/忽大忽小）
    - 基准 = 视频中位主体高度，使走路帧的平均体型与静止猫高度一致，
      走路全程体型既不小于也不明显大于静止猫
    - 画布尺寸取"所有帧统一比例后的最大宽/高 + 静止猫" + margin，
      保证任何迈步姿态都完整显示，且能容纳静止猫原图（用于最后一帧无缝衔接）
    - 每帧底边对齐 + 水平居中
    - 同时输出每帧"迈步累计位移比例"offsets（0~1），供 pet 只在实际迈步时移动窗口
    """
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频: {video_path}")

    # 第一遍：收集每帧主体尺寸与 x 中心
    metas = []  # (crop, x_center)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        out = np.array(remove(pil, session=session))
        res = _crop_alpha(out)
        if res is not None:
            crop, x0, _ = res
            x_center = x0 + crop.shape[1] // 2
            metas.append((crop, x_center))
    cap.release()
    if not metas:
        raise SystemExit(f"无法从视频取到任何有效帧: {video_path}")

    # 统一固定比例：以第一个迈步帧的主体高度为基准，缩放到与静止猫同高。
    # 所有帧用同一比例 -> 体型一致无渐变，且走路全程与静止猫等大
    # （否则中间帧偏小，切换动画时会出现"缩小再放大"的跳变）。
    h0 = metas[1][0].shape[0] if len(metas) > 1 else metas[0][0].shape[0]
    gscale = ref["ref_h"] / h0
    print(f"  walk 首迈步帧主体高 {h0}px -> 统一固定比例 {gscale:.4f}（与静止猫同高）")

    # 画布尺寸：容纳所有统一比例后帧 + 静止猫原图（最后一帧）
    scaled_w = [c.shape[1] * gscale for c, _ in metas]
    scaled_h = [c.shape[0] * gscale for c, _ in metas]
    cat_rgba = ref["cat_rgb"]  # 静止 cat 原图（用于首/尾帧无缝衔接）
    cat_w, cat_h = cat_rgba.shape[1], cat_rgba.shape[0]
    can_w = int(np.ceil(max(max(scaled_w), cat_w))) + margin
    can_h = int(np.ceil(max(max(scaled_h), cat_h))) + margin
    print(f"  walk 画布: {can_w}x{can_h}  统一比例后尺寸范围: 宽 {min(scaled_w):.0f}~{max(scaled_w):.0f} 高 {min(scaled_h):.0f}~{max(scaled_h):.0f}")

    # 迈步位移表：每帧 x 中心相对上一帧位移，超过阈值才视为实际迈步（消除静止期微动滑动）
    xs = [x for _, x in metas]
    diffs = [0.0]
    for i in range(1, len(xs)):
        d = abs(xs[i] - xs[i - 1])
        diffs.append(d if d >= 2.0 else 0.0)
    # 尾部收敛：动画末尾小猫已回到静止姿态，窗口应停止移动。
    # 将最后 TAIL_STILL 帧的位移置 0，使窗口提前到位并保持，切换静止画面时无滑动
    TAIL_STILL = 12
    if len(diffs) > TAIL_STILL + 2:
        for i in range(len(diffs) - TAIL_STILL, len(diffs)):
            diffs[i] = 0.0
    total = sum(diffs)
    if total > 0:
        cum = np.cumsum(diffs) / total
    else:
        cum = np.linspace(0, 1, len(diffs))
    with open(offsets_path, "w", encoding="utf-8") as f:
        json.dump([round(float(v), 5) for v in cum], f)
    print(f"  walk 位移表 -> {offsets_path}（{len(cum)} 帧，末尾 {TAIL_STILL} 帧静止收敛）")

    # 第二遍：逐帧缩放/色调/放置到独立画布
    cat_rgba = ref["cat_rgb"]  # 静止 cat 原图（用于首/尾帧无缝衔接）
    cat_w, cat_h = cat_rgba.shape[1], cat_rgba.shape[0]
    # 静止猫放到画布后的"可见底边"行：首/尾帧与中间帧都对齐到这里，
    # 而不是画布底边（cat.png 底部有几像素透明边距，对齐画布底边会下沉）
    cat_oy = can_h - cat_h
    bottom_y = cat_oy + ref["ref_y1"]
    for i, (crop, _) in enumerate(metas):
        canvas = np.zeros((can_h, can_w, 4), dtype=np.uint8)
        if i == 0 or i == len(metas) - 1:
            # 首/尾帧：直接用静止猫原图（水平居中 + 垂直底对齐放到 walk 画布），
            # 使动画开始/结束瞬间与静止画面位置、大小完全重合（无缝衔接）
            ox = (can_w - cat_w) // 2
            canvas[cat_oy:cat_oy + cat_h, ox:ox + cat_w] = cat_rgba
            Image.fromarray(canvas, "RGBA").save(os.path.join(out_dir, f"f{i:03d}.png"))
            print(f"  walk 首/尾帧 f{i:03d} = 静止猫原图（无缝衔接）")
            continue
        # 所有帧统一同一固定比例缩放（体型一致，无渐变）
        nw = max(1, int(round(crop.shape[1] * gscale)))
        nh = max(1, int(round(crop.shape[0] * gscale)))
        resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
        resized = _match_tone(resized, ref["cat_mean"], ref["cat_std"])

        x = (can_w - nw) // 2
        y = bottom_y - nh + 1  # 底边对齐静止猫可见底边
        x0c, x1c = max(0, x), min(can_w, x + nw)
        y0c, y1c = max(0, y), min(can_h, y + nh)
        rx0, ry0 = x0c - x, y0c - y
        canvas[y0c:y1c, x0c:x1c] = resized[ry0:ry0 + (y1c - y0c), rx0:rx0 + (x1c - x0c)]
        Image.fromarray(canvas, "RGBA").save(os.path.join(out_dir, f"f{i:03d}.png"))
    print(f"  walk 完成，共 {len(metas)} 帧 -> {out_dir}")


if __name__ == "__main__":
    ref = _load_cat_ref()
    print(f"画布: ({ref['can_w']}, {ref['can_h']})  主体 x[{ref['ref_x0']},{ref['ref_x1']}] y[{ref['ref_y0']},{ref['ref_y1']}]  色调均值 {[f'{v:.1f}' for v in ref['cat_mean'].values()]}")

    # 舔毛动画
    process_video_to_frames(
        video_path=os.path.join(ROOT_DIR, "source_media", "舔毛.mp4"),
        out_dir=os.path.join(ROOT_DIR, "assets", "_tianmao_frames"),
        ref=ref,
        include_cat_first=True,
    )

    # walkleft 动画（独立大画布 + 迈步位移表 + 与静止猫同大）
    process_walk_to_frames(
        video_path=os.path.join(ROOT_DIR, "source_media", "walkleft.mp4"),
        out_dir=os.path.join(ROOT_DIR, "assets", "_walkleft_frames"),
        ref=ref,
        offsets_path=os.path.join(ROOT_DIR, "assets", "_walk_offsets.json"),
    )