"""从 icon.png 生成高清多尺寸 icon.ico（用于 exe/窗口图标）。

Windows 会根据显示场景自动选择合适尺寸，因此需要包含 16/24/32/48/64/128/256
多个分辨率，避免资源管理器/任务栏拉伸模糊。
"""
import io
import struct
import numpy as np
from PIL import Image

CAT_IMG = "assets/icon.png"
ICON_OUT = "assets/icon.ico"


def _save_ico(images, path):
    """手动保存多尺寸 PNG-encoded ICO（Vista+ 格式）。"""
    png_data = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data.append(buf.getvalue())

    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = b""
    data = b""
    for img, png in zip(images, png_data):
        w, h = img.size
        bw = w if w < 256 else 0
        bh = h if h < 256 else 0
        size = len(png)
        entries += struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, size, offset)
        data += png
        offset += size

    with open(path, "wb") as f:
        f.write(header + entries + data)


def make_icon():
    cat = Image.open(CAT_IMG).convert("RGBA")
    arr = np.array(cat)
    alpha = arr[:, :, 3]
    nz = np.where(alpha > 10)
    x1, x2 = int(nz[1].min()), int(nz[1].max()) + 1
    y1, y2 = int(nz[0].min()), int(nz[0].max()) + 1

    # 留少量透明边距，避免图标贴边
    padding = 10
    x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
    x2, y2 = min(cat.width, x2 + padding), min(cat.height, y2 + padding)
    crop = cat.crop((x1, y1, x2, y2))

    # 以主体最大边为边长，居中放置到正方形画布
    size = max(crop.width, crop.height)
    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ox = (size - crop.width) // 2
    oy = (size - crop.height) // 2
    square.paste(crop, (ox, oy))

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [square.resize((s, s), Image.LANCZOS) for s in sizes]

    _save_ico(frames, ICON_OUT)
    print(f"已生成 {ICON_OUT}，尺寸: {sizes}")


if __name__ == "__main__":
    make_icon()
