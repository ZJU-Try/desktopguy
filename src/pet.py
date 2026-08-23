"""桌面宠物小猫 - 增强版。

功能：
- 无边框透明窗口，置顶显示在桌面上
- 平时静止待在桌面右下角
- 点击小猫触发"走动"动画（窗口向左移动，来源 walkleft.mp4）
- 每 8-10 秒随机触发三种原地动作之一：
  "舔毛"（来源 舔毛.mp4）、"原地动作1"（来源 原地动作1.mp4）、"原地动作2"（来源 原地动作2.mp4）
- 动画结束后回到静止状态，并重新开始 8-10 秒计时
- 所有状态均可拖动；拖动不打断当前动作，动画完成后才恢复静止并重新计时
- 动作进行中右键菜单的动作项灰显不可选，完成后恢复正常
- 拖动改变位置，右键菜单可退出

运行：.venv\\Scripts\\python.exe src\\pet.py
"""
import os
import sys
import json
import random
import enum
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

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAT_IMG = os.path.join(BASE_DIR, "assets", "cat.png")
LICK_DIR = os.path.join(BASE_DIR, "assets", "_tianmao_frames")
WALK_DIR = os.path.join(BASE_DIR, "assets", "_walkleft_frames")
ACTION1_DIR = os.path.join(BASE_DIR, "assets", "_action1_frames")
ACTION2_DIR = os.path.join(BASE_DIR, "assets", "_action2_frames")
WALK_OFFSETS = os.path.join(BASE_DIR, "assets", "_walk_offsets.json")
DEBUG_LOG = os.path.join(BASE_DIR, "pet_debug.log")


def _log(msg):
    try:
        import datetime
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
    except Exception:
        pass


class PetState(enum.Enum):
    IDLE = "idle"
    LICKING = "licking"
    WALKING = "walking"
    ACTION1 = "action1"
    ACTION2 = "action2"


class PetWindow(QGraphicsView):
    ANIM_FPS = 24
    IDLE_MIN_MS = 8000
    IDLE_MAX_MS = 10000
    WALK_MOVE_TOTAL = 180

    def __init__(self):
        super().__init__()
        self._pix = QPixmap(CAT_IMG)
        if self._pix.isNull():
            raise FileNotFoundError(f"找不到或无法加载图片: {CAT_IMG}")

        self._lick_frames = self._load_frames(LICK_DIR)
        self._walk_frames = self._load_frames(WALK_DIR)
        self._action1_frames = self._load_frames(ACTION1_DIR)
        self._action2_frames = self._load_frames(ACTION2_DIR)
        if not self._lick_frames:
            raise FileNotFoundError(f"找不到舔毛动画帧目录: {LICK_DIR}")
        if not self._walk_frames:
            raise FileNotFoundError(f"找不到走步动画帧目录: {WALK_DIR}")
        if not self._action1_frames:
            raise FileNotFoundError(f"找不到原地动作1动画帧目录: {ACTION1_DIR}")
        if not self._action2_frames:
            raise FileNotFoundError(f"找不到原地动作2动画帧目录: {ACTION2_DIR}")

        # walk 迈步位移表（0~1 累计比例），与实际迈步帧一一对应
        self._walk_offsets = []
        if os.path.exists(WALK_OFFSETS):
            try:
                with open(WALK_OFFSETS, "r", encoding="utf-8") as f:
                    self._walk_offsets = json.load(f)
            except Exception:
                self._walk_offsets = []
        if len(self._walk_offsets) != len(self._walk_frames):
            _log(f"警告: walk 位移表({len(self._walk_offsets)})与帧数({len(self._walk_frames)})不一致，回退为均匀移动")
            self._walk_offsets = None

        # walk 使用独立画布（比静止猫大，容纳迈步时完整身形）
        self._walk_canvas = self._walk_frames[0].size()
        ww, wh = self._walk_canvas.width(), self._walk_canvas.height()

        # 统一画布：把静止猫原图放到 walk 画布（水平居中 + 垂直底对齐）。
        self._idle_pix = QPixmap(ww, wh)
        self._idle_pix.fill(Qt.transparent)
        _p = QPainter(self._idle_pix)
        _p.drawPixmap(
            (ww - self._pix.width()) // 2,
            wh - self._pix.height(),
            self._pix,
        )
        _p.end()

        # 舔毛帧是 cat 原画布尺寸（165x220），需定位到统一画布的居中+底对齐位置
        lick_w, lick_h = self._lick_frames[0].width(), self._lick_frames[0].height()
        self._lick_offset = ((ww - lick_w) // 2, wh - lick_h)

        w, h = ww, wh

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setStyleSheet("background: transparent; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._scene = QGraphicsScene(0, 0, w, h)
        self.setScene(self._scene)

        self.cat_item = QGraphicsPixmapItem(self._idle_pix)
        self.cat_item.setPos(0, 0)
        self.cat_item.setTransformationMode(Qt.SmoothTransformation)
        self.cat_item.setCursor(Qt.PointingHandCursor)
        self._scene.addItem(self.cat_item)

        self.frame_item = QGraphicsPixmapItem()
        self.frame_item.setPos(0, 0)
        self.frame_item.setTransformationMode(Qt.SmoothTransformation)
        self.frame_item.setVisible(False)
        self._scene.addItem(self.frame_item)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(w, h)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - w - 40,
            screen.bottom() - h - 40,
        )

        # 状态
        self._state = PetState.IDLE
        self._frame_idx = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(int(1000 / self.ANIM_FPS))
        self._anim_timer.timeout.connect(self._on_tick)

        # 空闲自动走步计时器（单次触发）
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._schedule_idle_timer()

        # 拖拽状态
        self._press_global = None
        self._win_pos_at_press = None
        self._moved = False
        self._dragging = False

    def _load_frames(self, directory):
        if not os.path.isdir(directory):
            return []
        names = sorted(n for n in os.listdir(directory) if n.lower().endswith(".png"))
        frames = []
        for n in names:
            p = QPixmap(os.path.join(directory, n))
            if not p.isNull():
                frames.append(p)
        return frames

    def _schedule_idle_timer(self):
        """安排下一次自动动作的时间（8-10秒随机，从走步/动作1/动作2中随机选一个）。"""
        ms = random.randint(self.IDLE_MIN_MS, self.IDLE_MAX_MS)
        self._idle_timer.start(ms)
        _log(f"空闲计时器: {ms}ms 后自动动作")

    def _on_idle_timeout(self):
        """空闲超时 -> 随机触发 舔毛 / 原地动作1 / 原地动作2 之一（走步改为点击触发）。"""
        if self._state == PetState.IDLE:
            choice = random.choice([PetState.LICKING, PetState.ACTION1, PetState.ACTION2])
            _log(f"空闲超时 -> 随机触发 {choice.value}")
            if choice == PetState.LICKING:
                self._play_lick()
            else:
                self._play_anim(choice)

    # ---- 状态控制 ----
    def _set_state(self, new_state):
        self._state = new_state
        _log(f"状态: {new_state.value}")

    def _get_frames_for_state(self):
        if self._state == PetState.LICKING:
            return self._lick_frames
        elif self._state == PetState.WALKING:
            return self._walk_frames
        elif self._state == PetState.ACTION1:
            return self._action1_frames
        elif self._state == PetState.ACTION2:
            return self._action2_frames
        return []

    # ---- 播放控制 ----
    def _play_lick(self, force=False):
        """播放舔毛动画。force=True 时允许在任意状态下触发（右键菜单用）。"""
        if not force and self._state != PetState.IDLE:
            return
        self._idle_timer.stop()
        self._set_state(PetState.LICKING)
        self._frame_idx = 0
        self.cat_item.setVisible(False)
        self.frame_item.setPixmap(self._lick_frames[0])
        self.frame_item.setPos(*self._lick_offset)
        self.frame_item.setVisible(True)
        self._anim_timer.start()

    def _menu_play(self, state):
        """右键菜单触发：静止状态下播放对应动画（动作进行中菜单项已灰显）。"""
        if state == PetState.LICKING:
            self._play_lick(force=True)
        else:
            self._play_anim(state)

    def _play_anim(self, state):
        """播放走步 / 原地动作1 / 原地动作2 动画（统一画布，窗口无需 resize）。"""
        frames = {
            PetState.WALKING: self._walk_frames,
            PetState.ACTION1: self._action1_frames,
            PetState.ACTION2: self._action2_frames,
        }[state]
        self._idle_timer.stop()
        self._set_state(state)
        self._frame_idx = 0

        if state == PetState.WALKING:
            # 走步：记录窗口起点（底边始终对齐，仅水平位移）
            self._walk_base_x = self.x()
            self._walk_bottom = self.y() + self.height()
            _log(f"walk 开始: 起点 x={self._walk_base_x}")
        else:
            _log(f"{state.value} 开始（原地，窗口不动）")

        self.cat_item.setVisible(False)
        self.frame_item.setPixmap(frames[0])
        self.frame_item.setPos(0, 0)
        self.frame_item.setVisible(True)
        self._anim_timer.start()

    def _finish_anim(self):
        """结束原地动作：切回静止猫（与最后一帧同一画布，无闪烁）。"""
        name = self._state.value
        self._anim_timer.stop()
        self.frame_item.setVisible(False)
        self.cat_item.setVisible(True)
        self._set_state(PetState.IDLE)
        self._schedule_idle_timer()
        _log(f"{name} 结束，恢复静止")

    def _finish_walk(self):
        """结束走步：窗口尺寸不变，直接切回静止猫（与最后一帧同一画布，无闪烁）。"""
        self._anim_timer.stop()
        # 窗口尺寸已统一，无需 resize；猫底边始终对齐
        self.frame_item.setVisible(False)
        self.cat_item.setVisible(True)
        self._set_state(PetState.IDLE)
        self._schedule_idle_timer()
        _log(f"walk 结束，恢复静止，x={self.x()}")

    def _on_tick(self):
        frames = self._get_frames_for_state()
        self._frame_idx += 1
        if self._frame_idx >= len(frames):
            self._anim_timer.stop()
            if self._state == PetState.WALKING:
                self._finish_walk()
            elif self._state in (PetState.ACTION1, PetState.ACTION2):
                self._finish_anim()
            else:
                self.frame_item.setVisible(False)
                self.cat_item.setVisible(True)
                self._set_state(PetState.IDLE)
                self._schedule_idle_timer()
            return

        self.frame_item.setPixmap(frames[self._frame_idx])

        if self._state == PetState.WALKING:
            self._move_window_for_walk()

    def _move_window_for_walk(self):
        """只在视频中猫实际迈步的帧移动窗口（用位移表驱动）；拖拽时暂停自动移动。"""
        if self._dragging:
            return
        screen = QApplication.primaryScreen().availableGeometry()
        if self._walk_offsets is not None:
            # 用迈步位移累计比例：迈步帧前移，静止帧不动
            frac = self._walk_offsets[self._frame_idx]
            target_x = self._walk_base_x - self.WALK_MOVE_TOTAL * frac
        else:
            # 回退：均匀移动
            total_frames = len(self._walk_frames)
            target_x = self._walk_base_x - self.WALK_MOVE_TOTAL * (self._frame_idx / total_frames)
        target_x = max(float(target_x), float(screen.left()))
        self.move(int(round(target_x)), self.y())

    # ---- 交互：左键点击播放舔毛，拖动改变位置 ----
    DRAG_THRESHOLD = 6

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            hit = self._hit_cat(event.pos())
            _log(f"press 命中猫={hit} 状态={self._state.value}")
            if hit:
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
                if self._state == PetState.IDLE:
                    _log("release 点击 -> 触发走动")
                    self._play_anim(PetState.WALKING)
                else:
                    _log(f"release 点击但状态={self._state.value}，忽略")
            else:
                _log(f"release 拖拽结束 moved={self._moved}")
                if self._moved and self._state == PetState.WALKING:
                    # 拖拽后从新位置继续完成走步：以当前位置为基准衔接剩余位移
                    if self._walk_offsets is not None:
                        frac_now = self._walk_offsets[self._frame_idx]
                    else:
                        frac_now = self._frame_idx / len(self._walk_frames)
                    self._walk_base_x = self.x() + self.WALK_MOVE_TOTAL * frac_now
                    self._walk_bottom = self.y() + self.height()
                    _log(f"walk 拖拽衔接: 新基准 x={self._walk_base_x} frac={frac_now:.3f}")
            self._press_global = None
            self._dragging = False
            self._moved = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _hit_cat(self, pos):
        sp = self.mapToScene(pos)
        lx, ly = int(sp.x()), int(sp.y())
        # 统一画布后，静止猫用 _idle_pix（228x252），动画用 frame_item 当前帧
        item = self.cat_item if self._state == PetState.IDLE else self.frame_item
        pix = item.pixmap()
        if not pix.isNull():
            ox, oy = int(item.pos().x()), int(item.pos().y())
            rx, ry = lx - ox, ly - oy
            if 0 <= rx < pix.width() and 0 <= ry < pix.height():
                alpha = pix.toImage().pixelColor(rx, ry).alpha()
                return alpha > 10
        return False

    # ---- 右键菜单（简洁可爱风：圆角奶油色 + emoji 图标）----
    MENU_QSS = """
    QMenu {
        background-color: #fff6ee;
        border: 2px solid #ffd9c2;
        border-radius: 14px;
        padding: 6px;
        font-size: 13px;
        font-family: "Microsoft YaHei", "Segoe UI";
        color: #6b4f3a;
    }
    QMenu::item {
        padding: 7px 24px 7px 12px;
        border-radius: 8px;
        margin: 2px 4px;
        background: transparent;
    }
    QMenu::item:selected {
        background-color: #ffe3cf;
        color: #5a3a26;
    }
    QMenu::item:disabled {
        color: #cfbfae;
    }
    QMenu::separator {
        height: 1px;
        background: #f2ded0;
        margin: 5px 10px;
    }
    """

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self.MENU_QSS)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)

        # 有动作进行中时，所有动作项灰显不可选（退出始终可用）
        busy = self._state != PetState.IDLE

        def _add_item(text, state):
            act = QAction(text, menu)
            act.setEnabled(not busy)
            act.triggered.connect(lambda: self._menu_play(state))
            menu.addAction(act)

        _add_item("🐾  舔毛", PetState.LICKING)
        _add_item("🚶  走动", PetState.WALKING)
        _add_item("💃  动作 1", PetState.ACTION1)
        _add_item("🙌  动作 2", PetState.ACTION2)
        menu.addSeparator()
        act_quit = QAction("🚪  退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)
        menu.exec_(event.globalPos())


def main():
    import signal

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    def _on_sigint(*_):
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    pet = PetWindow()
    pet.show()
    _log("宠物启动（增强版：点击走动 + 原地随机动作）")
    print("桌面宠物已启动：点击触发走动，每 8-10 秒随机舔毛/动作1/动作2，可拖动，右键退出", flush=True)
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("已退出", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()