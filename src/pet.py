"""桌面宠物小猫 - baseline 版本。

功能：
- 无边框透明窗口，置顶显示在桌面上
- 平时静止待在桌面右下角
- 点击小猫后播放"舔毛"动画（逐帧透明序列，来源 舔毛.mp4）
- 动画结束后回到静止状态
- 右键菜单可退出

运行：.venv\Scripts\python.exe src\pet.py
"""
import os
import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QMenu,
    QAction,
)

# 打包兼容：PyInstaller 冻结运行时，数据文件解压到 _MEIPASS
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    # 脚本在 src/ 下，项目根目录是其上一级
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT_IMG = os.path.join(BASE_DIR, "assets", "cat.png")
ANIM_DIR = os.path.join(BASE_DIR, "assets", "_anim_frames")
DEBUG_LOG = os.path.join(BASE_DIR, "pet_debug.log")


def _log(msg):
    """追加写调试日志（用于排查交互问题）。"""
    try:
        import datetime
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
    except Exception:
        pass


class PetWindow(QGraphicsView):
    """无边框透明置顶的宠物窗口。"""

    ANIM_FPS = 24

    def __init__(self):
        super().__init__()
        self._pix = QPixmap(CAT_IMG)
        if self._pix.isNull():
            raise FileNotFoundError(f"找不到或无法加载图片: {CAT_IMG}")

        # 预加载动画帧
        self._frames = self._load_frames()
        if not self._frames:
            raise FileNotFoundError(f"找不到动画帧目录: {ANIM_DIR}")

        # 窗口与静止猫同尺寸，动画帧也缩放到该尺寸（与 cat.png 一致）
        w, h = self._pix.width(), self._pix.height()

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setStyleSheet("background: transparent; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._scene = QGraphicsScene(0, 0, w, h)
        self.setScene(self._scene)

        # 静止小猫：占满整个窗口
        self.cat_item = QGraphicsPixmapItem(self._pix)
        self.cat_item.setPos(0, 0)
        self.cat_item.setTransformationMode(Qt.SmoothTransformation)
        self.cat_item.setCursor(Qt.PointingHandCursor)
        self._scene.addItem(self.cat_item)

        # 动画帧图元（默认隐藏，与静止猫同位置，实现原地切换）
        self.frame_item = QGraphicsPixmapItem()
        self.frame_item.setPos(0, 0)
        self.frame_item.setTransformationMode(Qt.SmoothTransformation)
        self.frame_item.setVisible(False)
        self._scene.addItem(self.frame_item)

        # 窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(w, h)

        # 初始位置：屏幕右下角，留点边距
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - w - 40,
            screen.bottom() - h - 40,
        )

        # 动画状态
        self._playing = False
        self._frame_idx = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(int(1000 / self.ANIM_FPS))
        self._anim_timer.timeout.connect(self._on_tick)

        # 拖拽状态
        self._press_global = None
        self._win_pos_at_press = None
        self._moved = False
        self._dragging = False

    def _load_frames(self):
        if not os.path.isdir(ANIM_DIR):
            return []
        names = sorted(n for n in os.listdir(ANIM_DIR) if n.lower().endswith(".png"))
        frames = []
        for n in names:
            p = QPixmap(os.path.join(ANIM_DIR, n))
            if not p.isNull():
                frames.append(p)
        return frames

    # ---- 交互：左键点击播放动画，拖动改变位置 ----
    DRAG_THRESHOLD = 6  # 超过该像素视为拖拽

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            hit = self._hit_cat(event.pos())
            _log(f"press 命中猫={hit} 播放中={self._playing}")
            if hit:
                # 记录按下状态，等待判断是点击还是拖拽
                self._dragging = False
                self._press_global = event.globalPos()
                self._win_pos_at_press = self.pos()
                self._moved = False
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._press_global is not None:
            delta = event.globalPos() - self._press_global
            if not self._moved and (abs(delta.x()) >= self.DRAG_THRESHOLD or abs(delta.y()) >= self.DRAG_THRESHOLD):
                self._moved = True
                self._dragging = True
                _log(f"move 开始拖拽 delta=({delta.x()},{delta.y()})")
            if self._dragging:
                self.move(self._win_pos_at_press + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_global is not None:
            if not self._moved and self._hit_cat(event.pos()):
                # 未拖动且仍在猫上 -> 视为点击，播放动画
                _log("release 点击 -> 播放舔毛")
                self._play_anim()
            else:
                _log(f"release 拖拽结束 moved={self._moved}")
            self._press_global = None
            self._dragging = False
            self._moved = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _hit_cat(self, pos):
        """点击位置是否落在小猫不透明像素上（含动画播放时）。"""
        sp = self.mapToScene(pos)
        lx, ly = int(sp.x()), int(sp.y())
        pix = self.frame_item.pixmap() if self._playing else self._pix
        item = self.frame_item if self._playing else self.cat_item
        if not pix.isNull():
            # 图元坐标偏移
            ox, oy = int(item.pos().x()), int(item.pos().y())
            rx, ry = lx - ox, ly - oy
            if 0 <= rx < pix.width() and 0 <= ry < pix.height():
                alpha = pix.toImage().pixelColor(rx, ry).alpha()
                return alpha > 10
        return False

    def _play_anim(self):
        """点击后播放舔毛动画。"""
        if self._playing:
            return
        _log("动画开始播放")
        self._playing = True
        self._frame_idx = 0
        self.cat_item.setVisible(False)
        self.frame_item.setPixmap(self._frames[0])
        self.frame_item.setPos(0, 0)
        self.frame_item.setVisible(True)
        self._anim_timer.start()

    def _on_tick(self):
        self._frame_idx += 1
        if self._frame_idx >= len(self._frames):
            self._anim_timer.stop()
            self.frame_item.setVisible(False)
            self.cat_item.setVisible(True)
            self._playing = False
            return
        self.frame_item.setPixmap(self._frames[self._frame_idx])

    # ---- 右键菜单 ----
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)
        menu.exec_(event.globalPos())


def main():
    import signal

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Ctrl+C 优雅退出（不再打印 KeyboardInterrupt traceback）
    def _on_sigint(*_):
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    pet = PetWindow()
    pet.show()
    _log("宠物启动（新版：按下记录 / 释放播放 / 拖动移动）")
    print("桌面宠物已启动：点击播放舔毛动画，拖动改变位置，右键退出", flush=True)
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("已退出", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
