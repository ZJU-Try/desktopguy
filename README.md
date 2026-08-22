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
│   ├── make_animation.py    # 动画预处理（舔毛/walkleft/原地动作 mp4 -> 透明帧序列）
│   └── make_icon.py         # 从 cat.png 生成高清多尺寸 icon.ico
├── assets/
│   ├── cat.png              # 抠图后的透明背景小猫（静止显示）
│   ├── icon.ico             # 程序图标
│   ├── _tianmao_frames/     # 舔毛动画的透明帧序列（f000.png ~ f096.png，pet.py 播放）
│   ├── _walkleft_frames/    # 走步动画帧（f000~f144，统一画布 300x280）
│   ├── _action1_frames/     # 原地动作1动画帧（f000~f157）
│   ├── _action2_frames/     # 原地动作2动画帧（f000~f146）
│   └── _walk_offsets.json   # 走步迈步位移表（窗口只在迈步帧移动）
├── source_media/
│   ├── 蛋挞.jpg             # 小猫形象原图
│   ├── 舔毛.mp4             # 点击后播放的动画视频源
│   ├── walkleft.mp4         # 走步动画视频源
│   ├── 原地动作1.mp4        # 原地动作1视频源
│   └── 原地动作2.mp4        # 原地动作2视频源
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
- **每 8-10 秒随机触发三种自动动作之一**：
  - 走步（`walkleft.mp4`，窗口向左水平移动 180px）
  - 原地动作1（`原地动作1.mp4`，窗口不动）
  - 原地动作2（`原地动作2.mp4`，窗口不动）
- 动画播完自动回到静止
- **拖动小猫**：按住左键拖动改变位置（拖过 6px 判定为拖拽，否则判定为点击）
- **右键**：弹出菜单 → 退出

## 重新生成资源

换了形象原图或动画视频后，依次跑三个预处理脚本：

```powershell
# 1) 抠静止小猫图（跳过已下载模型，裁剪+缩放到 220px 高）
.\.venv\Scripts\python.exe src\make_assets.py

# 2) 从视频生成透明动画帧（存 assets\_tianmao_frames 和 assets\_walkleft_frames）
.\.venv\Scripts\python.exe src\make_animation.py

# 3) 生成高清程序图标（包含 16/24/32/48/64/128/256 多尺寸）
.\.venv\Scripts\python.exe src\make_icon.py
```

`make_animation.py` 保证动画与静止图无缝衔接：
1. **逐帧 AI 抠图**：用 rembg(u2net) 对每帧抠图——与 cat.png 同源抠图，色彩天然一致
2. **统一固定比例缩放**：所有帧用同一缩放比例，使猫体高度与静止猫完全一致，避免忽大忽小
3. **底边对齐 + 水平居中**：所有帧的猫脚底边对齐到静止猫的可见底边、水平居中，位置重合
4. **统一画布 320x280**：走步/原地动作共用同一画布，保证动作全程完整显示、不超出画布
5. **首/尾帧 = 静止猫原图**：动画开始/结束瞬间与静止画面完全重合，无跳变
6. **色调匹配**：逐帧颜色分布归一化到 cat.png，保证色调一致
7. **质心对齐（原地动作）**：每帧 alpha 加权质心固定对齐到静止猫质心，猫身视觉主体
   在动作全程稳定居中，避免视频中猫身整体漂移/突变造成的"偏移和跳变"

## 打包成免安装 exe

```powershell
cd d:\Code\desktopguy
.\.venv\Scripts\pyinstaller.exe --noconfirm --onefile --noconsole --name DesktopPet --icon=assets\icon.ico --add-data "assets\cat.png;assets" --add-data "assets\_tianmao_frames;assets\_tianmao_frames" --add-data "assets\_walkleft_frames;assets\_walkleft_frames" --add-data "assets\_action1_frames;assets\_action1_frames" --add-data "assets\_action2_frames;assets\_action2_frames" --add-data "assets\_walk_offsets.json;assets" src\pet.py
```

产物：`dist\DesktopPet.exe`（约 42MB 单文件），可直接拷到其他 Windows 电脑双击运行，无需安装 Python。

> 注意：PyInstaller 生成的 exe 可能被部分杀软误报，首次运行时需添加信任。

## 后续可扩展

- 多个动作随机触发
- 右键菜单增加"换动作""设置"
