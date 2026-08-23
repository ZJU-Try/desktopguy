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
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, pyqtSignal
from PyQt5.QtGui import (
    QPixmap,
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QFont,
    QFontMetrics,
)
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsProxyWidget,
    QLabel,
    QWidget,
    QDialog,
    QPushButton,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
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


# 四个可触发动作（点击/自动共用）
ACTIONS = [PetState.LICKING, PetState.WALKING, PetState.ACTION1, PetState.ACTION2]
# 显示名
ACTION_NAMES = {
    PetState.LICKING: "舔毛",
    PetState.WALKING: "走动",
    PetState.ACTION1: "动作 1",
    PetState.ACTION2: "动作 2",
}


# 每个动作 5 句随机台词
LINES = {
    PetState.LICKING: [
        "今天也要香香的～",
        "梳一梳，毛更顺啦",
        "舔毛时光，最享受",
        "喵～毛茸茸最可爱",
        "梳毛使我快乐",
    ],
    PetState.WALKING: [
        "出去散散步～",
        "是时候挪个窝了 ...",
        "溜达溜达，活动筋骨",
        "戳我干啥？",
        "散步时间到！",
    ],
    PetState.ACTION1: [
        "嘿嘿，看我表演！",
        "这个动作我练很久啦",
        "喵呜～接住我呀",
        "看我多灵活！",
        "跳起来！嘿咻！",
    ],
    PetState.ACTION2: [
        "转个圈圈～",
        "尾巴甩起来！",
        "喵喵，打个招呼",
        "看我甩尾巴多帅气",
        "今天心情超好！",
    ],
}

# 3 种对话框配色（背景 / 文字 / 边框）
BUBBLE_THEMES = [
    ("#fff7e0", "#8a6a2f", "#f2dc9a"),  # 奶油
    ("#ffe9f1", "#c25a78", "#f6b8cd"),  # 粉
    ("#e9f7f2", "#3f8a7a", "#a9e0d0"),  # 薄荷
]

# 3 种时髦字体（字体家族, 是否加粗）—— 随机出现
BUBBLE_FONTS = [
    ("幼圆", True),        # 可爱圆润
    ("华文行楷", False),   # 文艺潇洒
    ("方正舒体", False),   # 手写随性
]


class BubbleWidget(QWidget):
    """用 QPainter 直接绘制圆角气泡：四角完全透明，无 QSS 圆角的白色残角。

    带圆角背景 + 边框 + 居中文字，可自动换行，随内容自适应尺寸。
    """

    RADIUS = 14
    PAD_X = 13
    PAD_Y = 8
    FONT_SIZE = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._lines = []
        self._font = QFont("微软雅黑", self.FONT_SIZE)
        self._bg = QColor("#fff7e0")
        self._fg = QColor("#8a6a2f")
        self._bd = QColor("#f2dc9a")

    def set_content(self, text, bg, fg, bd, max_width, font_family="微软雅黑", bold=True):
        """设置台词、配色与字体，计算自适应尺寸（支持自动换行）。"""
        self._bg = QColor(bg)
        self._fg = QColor(fg)
        self._bd = QColor(bd)
        self._font = QFont(font_family, self.FONT_SIZE)
        self._font.setBold(bold)
        fm = QFontMetrics(self._font)
        self._lines = []
        for seg in text.split("\n"):
            line = ""
            for ch in seg:
                if fm.width(line + ch) > max_width - 2 * self.PAD_X and line:
                    self._lines.append(line)
                    line = ch
                else:
                    line += ch
            if line:
                self._lines.append(line)
        if not self._lines:
            self._lines = [""]
        w = max(fm.width(l) for l in self._lines) + 2 * self.PAD_X
        h = fm.height() * len(self._lines) + 2 * self.PAD_Y
        self.resize(max(w, 20), max(h, 20))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), self.RADIUS, self.RADIUS)
        p.fillPath(path, self._bg)
        p.setPen(QPen(self._bd, 2))
        p.drawPath(path)
        p.setPen(self._fg)
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        for i, line in enumerate(self._lines):
            y = self.PAD_Y + fm.ascent() + i * fm.height()
            p.drawText(QPointF((w - fm.width(line)) / 2, y), line)
        p.end()


class RangeSlider(QWidget):
    """双端点范围滑块：左/右端点固定为最小/最大值，中间两个可拖动节点设区间。

    范围 6~30 秒。拖动中发 valuesChanged（实时刷新显示），松开发 valuesCommitted（应用）。
    """

    MIN_VAL = 6
    MAX_VAL = 30
    TRACK_H = 10
    HANDLE_R = 11

    valuesChanged = pyqtSignal(int, int)
    valuesCommitted = pyqtSignal(int, int)

    def __init__(self, lo=8, hi=10, parent=None):
        super().__init__(parent)
        self._lo = int(lo)
        self._hi = int(hi)
        self._drag = None  # "lo" / "hi" / None
        self._font = QFont("微软雅黑", 10)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumHeight(70)

    def set_values(self, lo, hi):
        self._lo = int(lo)
        self._hi = int(hi)
        self.update()

    def values(self):
        return self._lo, self._hi

    # ---- 几何换算 ----
    def _track_x(self):
        return self.HANDLE_R + 6, self.width() - self.HANDLE_R - 6

    def _x_to_val(self, x):
        x0, x1 = self._track_x()
        span = self.MAX_VAL - self.MIN_VAL
        v = self.MIN_VAL + (x - x0) / (x1 - x0) * span
        return int(round(v))

    def _val_to_x(self, v):
        x0, x1 = self._track_x()
        span = self.MAX_VAL - self.MIN_VAL
        return int(x0 + (v - self.MIN_VAL) / span * (x1 - x0))

    # ---- 绘制 ----
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        x0, x1 = self._track_x()
        xlo, xhi = self._val_to_x(self._lo), self._val_to_x(self._hi)
        ty = h // 2 - self.TRACK_H // 2

        # 轨道底色
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f0e0d2"))
        p.drawRoundedRect(QRectF(x0, ty, x1 - x0, self.TRACK_H), 5, 5)
        # 高亮区间
        if xhi > xlo:
            p.setBrush(QColor("#ffb98a"))
            p.drawRoundedRect(QRectF(xlo, ty, xhi - xlo, self.TRACK_H), 5, 5)

        # 两端固定端点数值
        p.setPen(QColor("#b08b6a"))
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        p.drawText(QPointF(x0 - fm.width(str(self.MIN_VAL)) / 2, ty + self.TRACK_H + fm.height() + 2),
                   str(self.MIN_VAL))
        p.drawText(QPointF(x1 - fm.width(str(self.MAX_VAL)) / 2, ty + self.TRACK_H + fm.height() + 2),
                   str(self.MAX_VAL))

        # 两个可拖动节点（白色圆 + 橙点），上方显示当前值
        for v in (self._lo, self._hi):
            cx = self._val_to_x(v)
            cy = ty + self.TRACK_H / 2
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(cx, cy), self.HANDLE_R, self.HANDLE_R)
            p.setPen(QPen(QColor("#ffa06b"), 2))
            p.drawEllipse(QPointF(cx, cy), self.HANDLE_R - 2, self.HANDLE_R - 2)
            p.setPen(QColor("#e07b3a"))
            p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
            # 上方数值
            p.setPen(QColor("#d96a2b"))
            txt = str(v)
            p.drawText(QPointF(cx - fm.width(txt) / 2, cy - self.HANDLE_R - 4), txt)
        p.end()

    # ---- 交互 ----
    def mousePressEvent(self, event):
        x = event.pos().x()
        xlo, xhi = self._val_to_x(self._lo), self._val_to_x(self._hi)
        dlo, dhi = abs(x - xlo), abs(x - xhi)
        if min(dlo, dhi) <= self.HANDLE_R + 4:
            self._drag = "lo" if dlo <= dhi else "hi"
            self._update_drag(x)
        else:
            self._drag = None
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag:
            self._update_drag(event.pos().x())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag:
            self._drag = None
            self.valuesCommitted.emit(self._lo, self._hi)
        event.accept()

    def _update_drag(self, x):
        v = self._x_to_val(x)
        v = max(self.MIN_VAL, min(self.MAX_VAL, v))
        if self._drag == "lo":
            self._lo = min(v, self._hi)
        elif self._drag == "hi":
            self._hi = max(v, self._lo)
        self.update()
        self.valuesChanged.emit(self._lo, self._hi)


class SettingsDialog(QDialog):
    """设置窗口：与右键菜单同款奶油圆角风格，双端点滑块设置随机动作间隔。"""

    SETTINGS_QSS = """
    QLabel {
        background: transparent;
        color: #6b4f3a;
        font-family: "Microsoft YaHei", "Segoe UI";
    }
    QPushButton {
        background: #ffe3cf;
        color: #5a3a26;
        border: 1px solid #ffd0b0;
        border-radius: 10px;
        padding: 6px 16px;
        font-size: 13px;
        font-family: "Microsoft YaHei", "Segoe UI";
    }
    QPushButton:hover { background: #ffd9bf; }
    QPushButton:pressed { background: #ffcfa8; }
    """

    def __init__(self, pet, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self._pet = pet
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 440)
        self.setStyleSheet(self.SETTINGS_QSS)
        self._build_ui()
        self._update_hint()

    def _build_ui(self):
        # 标题行
        title = QLabel("⚙️  设置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #8a5a2f;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: #ffead9; border: none; border-radius: 14px;"
            " font-size: 18px; color: #b08060; }"
            "QPushButton:hover { background: #ffd9bf; color: #8a4a2a; }"
        )
        close_btn.clicked.connect(self.close)
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)

        # 小节标题（名称居左）
        desc = QLabel("随机动作间隔时间")
        desc.setStyleSheet("font-size: 13px; font-weight: bold; color: #8a5a2f;")

        # 双端点滑块
        self._slider = RangeSlider(8, 10)
        self._slider.valuesChanged.connect(self._on_values_changed)
        self._slider.valuesCommitted.connect(self._on_committed)

        # 当前值说明（小字，不加粗）
        self._val_label = QLabel("")
        self._val_label.setAlignment(Qt.AlignCenter)
        self._val_label.setStyleSheet("font-size: 11px; color: #9a7a5a;")

        # 分隔线
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.HLine)
        sep_line.setStyleSheet("QFrame { background: #f2ddc9; border: none; }")
        sep_line.setFixedHeight(1)

        # 点击动作 与 气泡开关 之间的分隔线
        sep_line2 = QFrame()
        sep_line2.setFrameShape(QFrame.HLine)
        sep_line2.setStyleSheet("QFrame { background: #f2ddc9; border: none; }")
        sep_line2.setFixedHeight(1)

        # 小节标题（名称居左）
        click_label = QLabel("点击小猫时触发的动作")
        click_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #8a5a2f;")
        self._combo = QComboBox()
        for st in ACTIONS:
            self._combo.addItem(ACTION_NAMES[st], st)
        self._combo.setFixedWidth(180)
        self._combo.setStyleSheet(
            "QComboBox { background: #ffffff; border: 1px solid #ffd0b0;"
            " border-radius: 8px; padding: 5px 12px; font-size: 13px; color: #6b4f3a;"
            " font-family: 'Microsoft YaHei', 'Segoe UI'; }"
            "QComboBox::drop-down { border: none; width: 22px; }"
            "QComboBox QAbstractItemView { background: #fff6ee; border: 1px solid #ffd0b0;"
            " border-radius: 6px; outline: none;"
            " selection-background-color: #ffe3cf; selection-color: #5a3a26; color: #6b4f3a; }"
        )
        self._combo.currentIndexChanged.connect(self._on_click_action_changed)

        # 气泡台词开关（名称居左 + 状态按钮居右，按钮带文字 开/关）
        bubble_label = QLabel("显示气泡台词")
        bubble_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #8a5a2f;")
        self._bubble_btn = QPushButton("开")
        self._bubble_btn.setFixedSize(70, 28)
        self._bubble_btn.setCursor(Qt.PointingHandCursor)
        self._bubble_btn.clicked.connect(self._toggle_bubble)
        self._update_bubble_btn()

        # 提示：其余 3 个动作将随机自动触发（放在触发动作选择下方，小字不加粗）
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet("font-size: 11px; color: #b08868;")

        # 底部按钮
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._on_reset)
        ok_btn = QPushButton("退出")
        ok_btn.clicked.connect(self.close)  # 只关闭设置窗口，不退出程序
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()

        # 统一设置区格式：第一行 = 名称(居左) + 控件(居右)；第二行(如有) = 小字说明
        # 随机动作间隔：名称第一行居左，滑块较长单独占一行
        name_row = QHBoxLayout()
        name_row.addWidget(desc)
        name_row.addStretch()
        # 点击动作：名称居左 + 下拉框居右
        click_row = QHBoxLayout()
        click_row.addWidget(click_label)
        click_row.addStretch()
        click_row.addWidget(self._combo)
        # 气泡开关：名称居左 + 状态按钮居右
        bubble_row = QHBoxLayout()
        bubble_row.addWidget(bubble_label)
        bubble_row.addStretch()
        bubble_row.addWidget(self._bubble_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 14, 26, 14)
        root.setSpacing(7)
        root.addLayout(title_row)
        root.addSpacing(2)
        root.addLayout(name_row)
        root.addWidget(self._slider)        # 滑块单独占一行
        root.addWidget(self._val_label)     # 说明小字
        root.addSpacing(8)
        root.addWidget(sep_line)
        root.addSpacing(8)
        root.addLayout(click_row)           # 名称 + 下拉框
        root.addWidget(self._hint)          # 提示放触发动作选择下方
        root.addSpacing(8)
        root.addWidget(sep_line2)
        root.addSpacing(8)
        root.addLayout(bubble_row)          # 名称 + 开关
        root.addStretch()
        root.addLayout(btn_row)

    # 圆角奶油背景（QPainter 绘制，避免 QSS 白角）
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 16, 16)
        p.fillPath(path, QColor("#fff6ee"))
        p.setPen(QPen(QColor("#ffd9c2"), 2))
        p.drawPath(path)
        p.end()

    def _on_click_action_changed(self, _idx):
        self._pet._set_click_action(self._combo.currentData())
        self._update_hint()

    def _toggle_bubble(self):
        """点击切换气泡台词开/关，并刷新按钮外观。"""
        self._pet._set_bubble_enabled(not self._pet._bubble_enabled)
        self._update_bubble_btn()

    def _update_bubble_btn(self):
        """刷新状态按钮：开=橙色，关=浅灰。"""
        if self._pet._bubble_enabled:
            self._bubble_btn.setText("开")
            self._bubble_btn.setStyleSheet(
                "QPushButton { background: #ffb98a; color: #ffffff;"
                " border: 1px solid #ffa06b; border-radius: 10px;"
                " padding: 3px 0; font-size: 13px; font-weight: bold;"
                " font-family: 'Microsoft YaHei', 'Segoe UI'; }"
                "QPushButton:hover { background: #ffa06b; }"
            )
        else:
            self._bubble_btn.setText("关")
            self._bubble_btn.setStyleSheet(
                "QPushButton { background: #f0e6dd; color: #9a8a7a;"
                " border: 1px solid #e3d3c4; border-radius: 10px;"
                " padding: 3px 0; font-size: 13px; font-weight: bold;"
                " font-family: 'Microsoft YaHei', 'Segoe UI'; }"
                "QPushButton:hover { background: #e8dbd0; }"
            )

    def _update_hint(self):
        """提示：点击触发动作为 X，其余 3 个动作随机自动触发。"""
        click = self._combo.currentData()
        others = [s for s in ACTIONS if s != click]
        names = "、".join(ACTION_NAMES[s] for s in others)
        self._hint.setText(
            f"点击触发：{ACTION_NAMES[click]}；\n其余（{names}）将随机自动触发"
        )

    def _on_values_changed(self, lo, hi):
        self._val_label.setText(f"当前：{lo} ~ {hi} 秒")
        self._update_hint()

    def _on_committed(self, lo, hi):
        self._pet._apply_interval(lo, hi)

    def _on_reset(self):
        """恢复默认：间隔 8~10 秒、点击动作=走动、气泡台词=开。"""
        self._slider.set_values(8, 10)
        self._pet._apply_interval(8, 10)
        self._on_values_changed(8, 10)
        idx = self._combo.findData(PetState.WALKING)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._pet._set_bubble_enabled(True)
        self._update_bubble_btn()
        self._update_hint()
        _log("设置已恢复默认: 间隔8~10s, 点击=走动, 气泡=开")

    def refresh_from_pet(self):
        lo = max(RangeSlider.MIN_VAL, self._pet.IDLE_MIN_MS // 1000)
        hi = min(RangeSlider.MAX_VAL, self._pet.IDLE_MAX_MS // 1000)
        self._slider.set_values(lo, hi)
        self._on_values_changed(lo, hi)
        idx = self._combo.findData(self._pet._click_action)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._update_bubble_btn()
        self._update_hint()

    def center_on_screen(self):
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.center() - QPoint(self.width() // 2, self.height() // 2))


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

        # 说话气泡（QPainter 圆角绘制 + ▼ 小尾巴），z 值置于猫之上
        self._bubble = BubbleWidget()
        self._bubble_proxy = self._scene.addWidget(self._bubble)
        self._bubble_proxy.setZValue(100)
        self._bubble_proxy.setVisible(False)
        self._tail = QLabel("▼")
        self._tail.setAttribute(Qt.WA_TranslucentBackground)
        self._tail_proxy = self._scene.addWidget(self._tail)
        self._tail_proxy.setZValue(101)
        self._tail_proxy.setVisible(False)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)
        self._win_w, self._win_h = w, h
        # 气泡台词开关（默认开启，可在设置中关闭）
        self._bubble_enabled = True

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

        # 设置窗口（首次打开时创建）
        self._settings_dialog = None
        # 点击触发动作（可右键菜单->设置中修改），其余 3 个作为自动触发池
        self._click_action = PetState.WALKING

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
        """空闲超时 -> 从其余 3 个动作中随机触发一个（点击动作不参与自动触发）。"""
        if self._state == PetState.IDLE:
            pool = [s for s in ACTIONS if s != self._click_action]
            choice = random.choice(pool)
            _log(f"空闲超时 -> 随机触发 {choice.value}")
            self._start_action(choice)

    def _start_action(self, state):
        """统一分发动作播放（点击 / 空闲自动共用）。"""
        if state == PetState.LICKING:
            self._play_lick()
        else:
            self._play_anim(state)

    def _set_click_action(self, state):
        """设置点击触发动作（设置窗口调用）。"""
        self._click_action = state
        _log(f"点击动作设置为: {state.value}")

    def _set_bubble_enabled(self, enabled):
        """设置气泡台词开关（设置窗口调用），关闭时立即隐藏当前气泡。"""
        self._bubble_enabled = bool(enabled)
        if not self._bubble_enabled:
            self._hide_bubble()
        _log(f"气泡台词: {'开' if enabled else '关'}")

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

    # ---- 说话气泡 ----
    def _show_bubble(self, state):
        """动作开始时弹出随机台词气泡：随机 1 句台词 + 随机 3 种样式 + 随机 3 种字体。"""
        if not self._bubble_enabled:
            return
        text = random.choice(LINES[state])
        bg, fg, bd = random.choice(BUBBLE_THEMES)
        font_family, bold = random.choice(BUBBLE_FONTS)
        self._bubble.set_content(text, bg, fg, bd, self._win_w - 16, font_family, bold)
        self._tail.setStyleSheet(
            f"QLabel {{ color: {bg}; background: transparent; border: none;"
            f" font-size: 14px; padding: 0; margin: 0; }}"
        )

        bw, bh = self._bubble.width(), self._bubble.height()
        bx = (self._win_w - bw) // 2
        by = 4
        self._bubble_proxy.setPos(bx, by)
        tw = self._tail.width()
        self._tail_proxy.setPos(bx + (bw - tw) // 2, by + bh - 3)
        self._bubble_proxy.setVisible(True)
        self._tail_proxy.setVisible(True)
        self._bubble_timer.start(random.randint(2200, 3200))
        _log(f"气泡: [{state.value}] {text}")

    def _hide_bubble(self):
        self._bubble_timer.stop()
        self._bubble_proxy.setVisible(False)
        self._tail_proxy.setVisible(False)

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
        self._show_bubble(PetState.LICKING)

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
        self._show_bubble(state)

    def _finish_anim(self):
        """结束原地动作：切回静止猫（与最后一帧同一画布，无闪烁）。"""
        name = self._state.value
        self._anim_timer.stop()
        self._hide_bubble()
        self.frame_item.setVisible(False)
        self.cat_item.setVisible(True)
        self._set_state(PetState.IDLE)
        self._schedule_idle_timer()
        _log(f"{name} 结束，恢复静止")

    def _finish_walk(self):
        """结束走步：窗口尺寸不变，直接切回静止猫（与最后一帧同一画布，无闪烁）。"""
        self._anim_timer.stop()
        self._hide_bubble()
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
                self._hide_bubble()
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
                    _log(f"release 点击 -> 触发 {self._click_action.value}")
                    self._start_action(self._click_action)
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
        act_settings = QAction("⚙️  设置", menu)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)
        menu.addSeparator()
        act_quit = QAction("🚪  退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)
        menu.exec_(event.globalPos())

    # ---- 设置窗口 ----
    def _open_settings(self):
        """屏幕中间弹出设置窗口（首次创建后复用）。"""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.refresh_from_pet()
        self._settings_dialog.center_on_screen()
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _apply_interval(self, lo_sec, hi_sec):
        """应用新的随机动作间隔（秒），并立即重启空闲计时器。"""
        self.IDLE_MIN_MS = lo_sec * 1000
        self.IDLE_MAX_MS = hi_sec * 1000
        if self._idle_timer.isActive():
            self._idle_timer.stop()
        if self._state == PetState.IDLE:
            self._schedule_idle_timer()
        _log(f"间隔设置: {lo_sec}s ~ {hi_sec}s")


def main():
    import signal

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 关闭任何子窗口（如设置窗口）都不退出程序；仅右键菜单"退出"显式退出
    app.setQuitOnLastWindowClosed(False)

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