"""
抠图：danta.jpg -> cat.png（透明背景），并裁剪到主体边界。

使用 u2net 模型（约 176MB），通过国内镜像加速下载。
"""
import os
import urllib.request
from PIL import Image

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_NAME = "u2net"
MODEL_FILE = f"{MODEL_NAME}.onnx"
# 把 rembg 数据目录设到项目内，避开沙箱对用户目录(~/.rembg)的写入限制
PROJECT_REMBG_HOME = os.path.join(ROOT_DIR, ".rembg")
os.environ.setdefault("REMBG_HOME", PROJECT_REMBG_HOME)
CACHE_DIR = os.path.join(PROJECT_REMBG_HOME, "models", MODEL_NAME)
MODEL_PATH = os.path.join(CACHE_DIR, MODEL_FILE)

SRC = os.path.join(ROOT_DIR, "source_media", "蛋挞.jpg")
OUT_RAW = os.path.join(ROOT_DIR, "assets", "cat_raw.png")
OUT = os.path.join(ROOT_DIR, "assets", "cat.png")


def download_model():
    """下载 u2net 模型，使用国内镜像加速"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # 检查模型是否已存在
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1_000_000:
        print(f"✓ 模型已存在: {MODEL_PATH}")
        return
    
    # 镜像源列表（优先使用国内加速镜像）
    MIRRORS = [
        "https://hf-mirror.com/danielgatis/rembg/resolve/main/u2net.onnx",  # HuggingFace 国内镜像
        "https://ghfast.top/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
        "https://ghproxy.net/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
        "https://hub.gitmirror.com/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
        "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",  # 官方源，最后尝试
    ]
    
    for i, url in enumerate(MIRRORS, 1):
        print(f"\n尝试镜像 [{i}/{len(MIRRORS)}]: {url}")
        try:
            # 获取文件大小
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                total = int(resp.headers.get("Content-Length", 0))
            
            if not total:
                raise RuntimeError("无法获取文件大小")
            
            print(f"文件大小: {total/1e6:.1f} MB")
            
            # 下载文件
            tmp_path = MODEL_PATH + ".tmp"
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            
            print("开始下载（请耐心等待，约需1-5分钟）...")
            with urllib.request.urlopen(req, timeout=300) as resp:
                with open(tmp_path, "wb") as f:
                    downloaded = 0
                    last_print = 0
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1MB 块
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        # 每 2% 打印一次进度，减少刷屏
                        progress = int(downloaded / total * 100)
                        if progress >= last_print + 2:
                            print(f"\r进度: {downloaded/1e6:.1f}/{total/1e6:.1f} MB ({progress}%)", end="")
                            last_print = progress
            print("\n✓ 下载完成")
            
            os.replace(tmp_path, MODEL_PATH)
            print(f"✓ 模型已保存: {MODEL_PATH}")
            return
            
        except Exception as e:
            print(f"\n✗ 失败: {e}")
            # 清理临时文件
            if os.path.exists(MODEL_PATH + ".tmp"):
                try:
                    os.remove(MODEL_PATH + ".tmp")
                except:
                    pass
    
    # 所有镜像都失败
    print("\n" + "="*60)
    print("所有镜像均下载失败！请尝试手动下载：")
    print("1. 使用浏览器/下载工具打开以下链接：")
    print("   https://hf-mirror.com/danielgatis/rembg/resolve/main/u2net.onnx")
    print("2. 下载后放到以下路径：")
    print(f"   {MODEL_PATH}")
    print("="*60)
    raise RuntimeError("模型下载失败")


def remove_bg():
    """抠图并裁剪到主体边界"""
    try:
        from rembg import remove, new_session
    except ImportError:
        print("请先安装 rembg: pip install rembg")
        raise
    
    print("\n正在加载模型...")
    session = new_session("u2net_custom", model_path=MODEL_PATH)
    
    print(f"正在处理图片: {SRC}")
    with open(SRC, "rb") as f:
        data = remove(f.read(), session=session)
    
    with open(OUT_RAW, "wb") as f:
        f.write(data)
    print(f"✓ 抠图完成: {OUT_RAW}")
    
    # 裁剪到主体边界并缩放
    print("正在裁剪和缩放...")
    im = Image.open(OUT_RAW).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
        print(f"  裁剪边界: {bbox}")
    else:
        print("  警告: 未检测到主体")
    
    # 缩放高度到 220px
    target_h = 220
    w, h = im.size
    if h > target_h:
        new_w = int(w * target_h / h)
        im = im.resize((new_w, target_h), Image.LANCZOS)
        print(f"  缩放至: {im.size}")
    
    im.save(OUT)
    print(f"✓ 最终图片已保存: {OUT}")
    print(f"  最终尺寸: {im.size}")


if __name__ == "__main__":
    print("="*60)
    print("抠图工具 - 将 danta.jpg 抠出透明背景 cat.png")
    print("="*60)
    
    # 检查源文件是否存在
    if not os.path.exists(SRC):
        print(f"错误: 源文件不存在: {SRC}")
        exit(1)
    
    download_model()
    remove_bg()
    
    print("\n" + "="*60)
    print("✓ 所有操作完成！")
    print("="*60)