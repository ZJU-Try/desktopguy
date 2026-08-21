# desktopguy - 桌面宠物小猫（baseline）

把 `蛋挞.jpg` 里的小猫做成桌面宠物，类似 QQ 宠物：平时静止待在桌面，点击后播放"舔毛"动画。

## 技术栈

- Python 3.11 + PyQt5（无边框透明置顶窗口 + 图元动画）
- Pillow（图像裁剪缩放）
- rembg + u2net.onnx（AI 抠图，生成透明背景 PNG）
- OpenCV（视频抽帧）+ 色键抠图（生成透明动画帧序列）

## 环境准备

已配置好本地 venv `.venv`，依赖均已安装。pip 已切到清华镜像。

## 目录结构

```
desktopguy/
├── src/
│   ├── pet.py               # 桌面宠物主程序
│   ├── make_assets.py       # 抠图脚本（生成 cat.png）
│   └── make_animation.py    # 动画预处理（舔毛.mp4 -> _anim_frames）
├── assets/
│   ├── cat.png              # 抠图后的透明背景小猫（静止显示）
│   ├── icon.ico             # 程序图标
│   └── _anim_frames/        # 舔毛动画的透明帧序列（f000.png ~ f096.png，pet.py 播放）
├── source_media/
│   ├── 蛋挞.jpg             # 小猫形象原图
│   └── 舔毛.mp4             # 点击后播放的动画视频源
├── .rembg/models/u2net/u2net.onnx   # AI 抠图模型（176MB，已下载）
├── .venv/                   # 本地虚拟环境
├── dist/                    # PyInstaller 打包产物
├── DesktopPet.spec          # 打包配置
└── README.md
```

## 运行

```powershell
cd d:\Code\desktopguy
.\.venv\Scripts\python.exe src\pet.py
```

## 功能

- 小猫以透明窗口形式出现在桌面右下角，始终置顶
- 平时静止显示 `蛋挞.jpg` 抠出的猫
- **点击小猫**：播放"舔毛"动画（来自 `舔毛.mp4`，AI 抠图后的透明逐帧，约 4 秒）
- 动画播完自动回到静止
- **拖动小猫**：按住左键拖动改变位置（拖过 6px 判定为拖拽，否则判定为点击）
- **右键**：弹出菜单 → 退出

## 重新生成资源

换了形象原图或动画视频后，依次跑两个预处理脚本：

```powershell
# 1) 抠静止小猫图（跳过已下载模型，裁剪+缩放到 220px 高）
.\.venv\Scripts\python.exe src\make_assets.py

# 2) 从视频生成透明动画帧（存 assets\_anim_frames）
.\.venv\Scripts\python.exe src\make_animation.py
```

`make_animation.py` 保证动画与静止图无缝衔接：
1. **逐帧 AI 抠图**：用 rembg(u2net) 对每帧抠图——与 cat.png 同源抠图，色彩天然一致
2. **按主体 bbox 对齐**：裁剪抠图主体并缩放到 cat.png 同尺寸（165x220），大小位置一致

## 打包成免安装 exe

```powershell
cd d:\Code\desktopguy
.\.venv\Scripts\pyinstaller.exe --noconfirm --onefile --noconsole --name DesktopPet --icon=assets\icon.ico --add-data "assets\cat.png;assets" --add-data "assets\_anim_frames;assets\_anim_frames" src\pet.py
```

产物：`dist\DesktopPet.exe`（约 42MB 单文件），可直接拷到其他 Windows 电脑双击运行，无需安装 Python。

> 注意：PyInstaller 生成的 exe 可能被部分杀软误报，首次运行时需添加信任。

## 后续可扩展

- 多个动作随机触发
- 右键菜单增加"换动作""设置"
