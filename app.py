"""Review Margin — desktop app.

Open a portrait paper, preview it on landscape pages with a notes area on the
right, and export the result for GoodNotes / Notability.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pymupdf
from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF,
    QSettings, QSize, Qt, QThread, QTimer, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPainter,
    QPainterPath, QPalette, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QFileDialog, QFileIconProvider, QFrame,
    QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from margin_core import STYLES, Options, build, convert_file, default_output

APP = "Review Margin"
MAC = sys.platform == "darwin"

LIGHT = dict(
    sidebar="#f5f5f7", canvas="#e9e9ee", card="#ffffff", text="#1d1d1f",
    secondary="#6e6e73", tertiary="#aeaeb2", border="#d9d9de", hover="#ececf0",
    accent="#0071e3", accent_hover="#0077ed", accent_pressed="#006edb",
    track="#e3e3e8", seg="#ffffff", switch_off="#d9d9de", shadow=18,
)
DARK = dict(
    sidebar="#1f1f21", canvas="#141415", card="#2c2c2e", text="#f5f5f7",
    secondary="#98989d", tertiary="#636366", border="#3a3a3c", hover="#343437",
    accent="#0a84ff", accent_hover="#2491ff", accent_pressed="#0077ed",
    track="#2c2c2e", seg="#5a5a5e", switch_off="#48484a", shadow=40,
)
T = dict(LIGHT)  # current theme, updated in place on light/dark switch


def is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return QGuiApplication.palette().window().color().lightness() < 128


def stylesheet() -> str:
    return f"""
    * {{ font-size: 13px; color: {T['text']}; }}
    QMainWindow, #sidebar {{ background: {T['sidebar']}; }}
    #sidebar {{ border-right: 1px solid {T['border']}; }}
    #appName {{ font-size: 15px; font-weight: 600; }}
    #section {{ font-size: 11px; font-weight: 600; color: {T['secondary']}; }}
    #secondary, #value {{ color: {T['secondary']}; }}
    #card {{ background: {T['card']}; border: 1px solid {T['border']}; border-radius: 10px; }}
    #fileName {{ font-weight: 600; }}
    #placeholder {{ color: {T['tertiary']}; }}

    QPushButton {{
        background: {T['card']}; border: 1px solid {T['border']}; border-radius: 7px;
        padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {T['hover']}; }}
    QPushButton#primary {{
        background: {T['accent']}; border: none; color: white; font-weight: 600;
        border-radius: 8px; padding: 9px 0;
    }}
    QPushButton#primary:hover {{ background: {T['accent_hover']}; }}
    QPushButton#primary:pressed {{ background: {T['accent_pressed']}; }}
    QPushButton#primary:disabled {{ background: {T['track']}; color: {T['tertiary']}; }}
    QPushButton#link {{
        background: transparent; border: none; padding: 0; color: {T['accent']};
    }}
    QPushButton#link:hover {{ text-decoration: underline; }}

    #segmented {{ background: {T['track']}; border-radius: 8px; }}
    #segmented QPushButton {{
        background: transparent; border: 1px solid transparent; border-radius: 6px;
        padding: 4px 0; color: {T['secondary']};
    }}
    #segmented QPushButton:hover {{ color: {T['text']}; }}
    #segmented QPushButton:checked {{
        background: {T['seg']}; color: {T['text']}; border: 1px solid {T['border']};
    }}

    QSlider {{ min-height: 22px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {T['track']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {T['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: white; border: 1px solid {T['border']};
        width: 18px; height: 18px; margin: -8px 0; border-radius: 9px;
    }}

    #pill {{ background: {T['card']}; border: 1px solid {T['border']}; border-radius: 15px; }}
    #pill QPushButton {{
        background: transparent; border: none; padding: 0 10px; font-size: 16px;
        color: {T['secondary']};
    }}
    #pill QPushButton:hover {{ color: {T['text']}; }}
    #pill QPushButton:disabled {{ color: {T['tertiary']}; }}
    #pageLabel {{ color: {T['secondary']}; font-size: 12px; }}

    QMenu {{ background: {T['card']}; border: 1px solid {T['border']}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {T['accent']}; color: white; }}
    QToolTip {{ background: {T['card']}; color: {T['text']}; border: 1px solid {T['border']}; }}
    """


def apply_theme(app: QApplication) -> None:
    T.update(DARK if is_dark() else LIGHT)
    pal = app.style().standardPalette()
    for role, key in ((QPalette.Window, "sidebar"), (QPalette.Base, "card"),
                      (QPalette.AlternateBase, "hover"), (QPalette.Button, "card"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.ToolTipBase, "card"), (QPalette.ToolTipText, "text")):
        pal.setColor(role, QColor(T[key]))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def resource(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


def reveal(path: Path) -> None:
    if MAC:
        subprocess.run(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)])
    else:
        subprocess.run(["xdg-open", str(path.parent)])


def pretty_dir(d: Path) -> str:
    home = str(Path.home())
    return "~" + str(d)[len(home):] if str(d).startswith(home) else str(d)


def human_size(n: float) -> str:
    for unit in ("bytes", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ---------------------------------------------------------------- widgets

class Switch(QAbstractButton):
    """macOS-style toggle with an animated knob."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(36, 21)
        self._k = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(36, 21)

    def _get(self):
        return self._k

    def _set(self, v):
        self._k = v
        self.update()

    knob = Property(float, _get, _set)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._k)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(T["switch_off"]), QColor(T["accent"])
        k = self._k
        mix = QColor.fromRgbF(off.redF() + (on.redF() - off.redF()) * k,
                              off.greenF() + (on.greenF() - off.greenF()) * k,
                              off.blueF() + (on.blueF() - off.blueF()) * k)
        p.setPen(Qt.NoPen)
        p.setBrush(mix)
        p.drawRoundedRect(QRectF(0, 0.5, 36, 20), 10, 10)
        x = 2 + k * 16
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawEllipse(QRectF(x, 3.1, 16, 16))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 2.5, 16, 16))


class Segmented(QFrame):
    changed = Signal(int)

    def __init__(self, labels: list[str], current: int):
        super().__init__(objectName="segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(i == current)
            self.group.addButton(b, i)
            lay.addWidget(b)
        self.group.idClicked.connect(self.changed)

    def current(self) -> int:
        return self.group.checkedId()


class Canvas(QWidget):
    """Shows the page with a soft shadow, or a drop zone when empty."""

    fileDropped = Signal(Path)
    resized = Signal()

    MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 44, 36, 76

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumSize(420, 320)
        self.pix: QPixmap | None = None
        self.aspect = 4 / 3
        self.hover = False

        self.open_btn = QPushButton("Choose File…", self)
        self.open_btn.setCursor(Qt.PointingHandCursor)

        self.pill = QFrame(self, objectName="pill")
        pl = QHBoxLayout(self.pill)
        pl.setContentsMargins(4, 0, 4, 0)
        pl.setSpacing(0)
        self.prev_btn = QPushButton("‹")
        self.page_label = QLabel("", objectName="pageLabel", alignment=Qt.AlignCenter)
        self.page_label.setMinimumWidth(72)
        self.next_btn = QPushButton("›")
        for w in (self.prev_btn, self.page_label, self.next_btn):
            w.setCursor(Qt.PointingHandCursor)
            pl.addWidget(w)
        self.pill.setFixedHeight(30)
        self.pill.hide()

    def page_rect(self, aspect: float | None = None) -> QRectF:
        a = aspect or self.aspect
        avail = QRectF(self.rect()).adjusted(self.MARGIN_X, self.MARGIN_TOP,
                                             -self.MARGIN_X, -self.MARGIN_BOTTOM)
        w = min(avail.width(), avail.height() * a)
        h = w / a
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h)

    def drop_rect(self) -> QRectF:
        w, h = min(440, self.width() - 80), min(280, self.height() - 80)
        c = QRectF(self.rect()).center()
        return QRectF(c.x() - w / 2, c.y() - h / 2, w, h)

    def layout_overlays(self):
        r = self.drop_rect()
        self.open_btn.adjustSize()
        self.open_btn.move(int(r.center().x() - self.open_btn.width() / 2), int(r.center().y() + 26))
        self.pill.adjustSize()
        self.pill.move(int(self.width() / 2 - self.pill.width() / 2), self.height() - 52)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layout_overlays()
        self.resized.emit()

    def set_page(self, pix: QPixmap, aspect: float):
        self.pix, self.aspect = pix, aspect
        self.open_btn.hide()
        self.pill.show()
        self.layout_overlays()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(T["canvas"]))
        if self.pix is None:
            self._paint_empty(p)
            return
        r = self.page_rect()
        p.setPen(Qt.NoPen)
        step = max(1, T["shadow"] // 14)
        for i in range(1, 15):  # soft shadow
            p.setBrush(QColor(0, 0, 0, step))
            p.drawRoundedRect(r.adjusted(-i, -i + 4, i, i + 4), 3 + i, 3 + i)
        path = QPainterPath()
        path.addRoundedRect(r, 3, 3)
        p.setClipPath(path)
        p.drawPixmap(r, self.pix, QRectF(self.pix.rect()))

    def _paint_empty(self, p: QPainter):
        r = self.drop_rect()
        accent = QColor(T["accent"])
        if self.hover:
            fill = QColor(accent)
            fill.setAlpha(22)
            p.setBrush(fill)
        else:
            p.setBrush(Qt.NoBrush)
        pen = QPen(accent if self.hover else QColor(T["tertiary"]), 1.5)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 16, 16)

        # glyph: a landscape sheet with text on the left, lines on the right
        c = r.center()
        g = QRectF(c.x() - 28, c.y() - 92, 56, 40)
        p.setPen(QPen(accent if self.hover else QColor(T["tertiary"]), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(g, 5, 5)
        mid = g.left() + g.width() * 0.55
        p.drawLine(QPointF(mid, g.top() + 6), QPointF(mid, g.bottom() - 6))
        for i in range(3):
            y = g.top() + 12 + i * 8
            p.drawLine(QPointF(g.left() + 7, y), QPointF(mid - 6, y))
            p.drawLine(QPointF(mid + 5, y), QPointF(g.right() - 6, y))

        f = QFont(self.font())
        f.setPixelSize(17)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T["text"]))
        p.drawText(QRectF(r.left(), c.y() - 38, r.width(), 24), Qt.AlignCenter, "Drop a paper here")
        f.setPixelSize(13)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(QColor(T["secondary"]))
        p.drawText(QRectF(r.left(), c.y() - 12, r.width(), 20), Qt.AlignCenter,
                   "It opens in landscape, with room for your notes")

    @staticmethod
    def _pdf(e) -> Path | None:
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                return Path(u.toLocalFile())
        return None

    def dragEnterEvent(self, e):
        if self._pdf(e):
            e.acceptProposedAction()
            self.hover = True
            self.update()

    def dragLeaveEvent(self, e):
        self.hover = False
        self.update()

    def dropEvent(self, e):
        self.hover = False
        self.update()
        if f := self._pdf(e):
            self.fileDropped.emit(f)


class Exporter(QObject):
    done = Signal(str, int)
    failed = Signal(str)

    def __init__(self, src: Path, dst: Path, opts: Options):
        super().__init__()
        self.src, self.dst, self.opts = src, dst, opts

    def run(self):
        try:
            self.done.emit(str(self.dst), convert_file(self.src, self.dst, self.opts))
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------- window

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ReviewMargin", APP)
        self.src_path: Path | None = None
        self.doc: pymupdf.Document | None = None
        self.page = 0
        self.out_dir: Path | None = None
        self.last_output: Path | None = None
        self.thread: QThread | None = None

        self.setWindowTitle(APP)
        self.setMinimumSize(900, 580)
        geo = self.settings.value("geometry")
        if not (geo and self.restoreGeometry(geo)):
            self.resize(1200, 760)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.render)

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._sidebar())
        self.canvas = Canvas()
        self.canvas.fileDropped.connect(self.load)
        self.canvas.open_btn.clicked.connect(self.choose_file)
        self.canvas.prev_btn.clicked.connect(lambda: self.go(-1))
        self.canvas.next_btn.clicked.connect(lambda: self.go(1))
        self.canvas.resized.connect(self.timer.start)
        lay.addWidget(self.canvas, 1)
        self.setCentralWidget(root)

        self._menus()
        self.refresh()

    # layout ---------------------------------------------------------
    def _menus(self):
        self.open_act = QAction("Open…", self, shortcut=QKeySequence.Open, triggered=self.choose_file)
        self.export_act = QAction("Export PDF", self, shortcut=QKeySequence("Ctrl+E"), triggered=self.export)
        self.reveal_act = QAction("Show Last Export", self, triggered=self.reveal_last)
        prev_act = QAction("Previous Page", self, shortcut=QKeySequence(Qt.Key_Left),
                           triggered=lambda: self.go(-1))
        next_act = QAction("Next Page", self, shortcut=QKeySequence(Qt.Key_Right),
                           triggered=lambda: self.go(1))
        self.addActions([self.open_act, self.export_act, prev_act, next_act])
        if MAC:  # native menu bar; on Windows the window stays chrome-free
            m = self.menuBar().addMenu("File")
            m.addActions([self.open_act, self.export_act])
            m.addSeparator()
            m.addAction(self.reveal_act)
            self.menuBar().addMenu("View").addActions([prev_act, next_act])
        else:
            self.menuBar().hide()

    @staticmethod
    def _row(left: QWidget, right: QWidget) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(left)
        h.addStretch()
        h.addWidget(right)
        return h

    def _sidebar(self) -> QWidget:
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(284)
        v = QVBoxLayout(side)
        v.setContentsMargins(20, 22, 20, 20)
        v.setSpacing(0)

        v.addWidget(QLabel(APP, objectName="appName"))
        v.addSpacing(24)

        # paper
        open_link = QPushButton("Open…", objectName="link")
        open_link.setCursor(Qt.PointingHandCursor)
        open_link.clicked.connect(self.choose_file)
        v.addLayout(self._row(QLabel("Paper", objectName="section"), open_link))
        v.addSpacing(8)
        card = QFrame(objectName="card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(2)
        self.file_name = QLabel("No paper open", objectName="placeholder")
        self.file_meta = QLabel("", objectName="secondary")
        self.file_meta.hide()
        cv.addWidget(self.file_name)
        cv.addWidget(self.file_meta)
        v.addWidget(card)
        v.addSpacing(28)

        # layout
        v.addWidget(QLabel("Layout", objectName="section"))
        v.addSpacing(12)
        self.width_value = QLabel("", objectName="value")
        v.addLayout(self._row(QLabel("Notes width"), self.width_value))
        v.addSpacing(4)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(20, 60)
        self.slider.setPageStep(5)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setValue(int(self.settings.value("notes", 45)))
        self.slider.valueChanged.connect(self.options_changed)
        v.addWidget(self.slider)
        v.addSpacing(16)

        v.addWidget(QLabel("Background"))
        v.addSpacing(6)
        style = self.settings.value("style", "lines")
        self.segment = Segmented([s.capitalize() for s in STYLES],
                                 STYLES.index(style) if style in STYLES else 1)
        self.segment.changed.connect(self.options_changed)
        v.addWidget(self.segment)
        v.addSpacing(18)

        self.divider = Switch(self.settings.value("divider", "true") in (True, "true"))
        self.divider.toggled.connect(self.options_changed)
        v.addLayout(self._row(QLabel("Divider line"), self.divider))

        v.addStretch()

        # save to
        v.addWidget(QLabel("Save to", objectName="section"))
        v.addSpacing(8)
        folder = QFrame(objectName="card")
        fl = QHBoxLayout(folder)
        fl.setContentsMargins(10, 8, 12, 8)
        fl.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(QFileIconProvider().icon(QFileIconProvider.Folder).pixmap(16, 16))
        self.out_label = QLabel("")
        change = QPushButton("Change", objectName="link")
        change.setCursor(Qt.PointingHandCursor)
        menu = QMenu(change)
        menu.addAction("Same Folder as Paper", lambda: self.set_out_dir(None))
        menu.addAction("Choose Folder…", self.choose_folder)
        change.clicked.connect(lambda: menu.exec(change.mapToGlobal(change.rect().bottomLeft())))
        fl.addWidget(icon)
        fl.addWidget(self.out_label, 1)
        fl.addWidget(change)
        v.addWidget(folder)
        saved = self.settings.value("out_dir", "")
        self.set_out_dir(Path(saved) if saved and Path(saved).is_dir() else None)
        v.addSpacing(14)

        self.export_btn = QPushButton("Export PDF", objectName="primary")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self.export)
        v.addWidget(self.export_btn)
        v.addSpacing(10)

        self.status = QLabel("", objectName="secondary")
        self.reveal_btn = QPushButton("Show in Finder" if MAC else "Show in Explorer", objectName="link")
        self.reveal_btn.setCursor(Qt.PointingHandCursor)
        self.reveal_btn.clicked.connect(self.reveal_last)
        self.reveal_btn.hide()
        box = QWidget()
        box.setLayout(self._row(self.status, self.reveal_btn))
        box.setFixedHeight(18)
        v.addWidget(box)
        return side

    # state ----------------------------------------------------------
    def options(self) -> Options:
        return Options(notes=self.slider.value() / 100, style=STYLES[self.segment.current()],
                       divider=self.divider.isChecked())

    def options_changed(self, *_):
        o = self.options()
        self.settings.setValue("notes", self.slider.value())
        self.settings.setValue("style", o.style)
        self.settings.setValue("divider", "true" if o.divider else "false")
        self.width_value.setText(f"{self.slider.value()}%")
        self.timer.start()

    def refresh(self):
        has = self.doc is not None
        n = len(self.doc) if has else 0
        busy = self.thread is not None
        self.export_btn.setEnabled(has and not busy)
        self.export_btn.setText("Exporting…" if busy else "Export PDF")
        self.export_act.setEnabled(has and not busy)
        self.reveal_act.setEnabled(self.last_output is not None)
        self.canvas.prev_btn.setEnabled(has and self.page > 0)
        self.canvas.next_btn.setEnabled(has and self.page < n - 1)
        self.canvas.page_label.setText(f"{self.page + 1} of {n}" if has else "")
        self.width_value.setText(f"{self.slider.value()}%")

    def set_out_dir(self, d: Path | None):
        self.out_dir = d
        self.settings.setValue("out_dir", str(d) if d else "")
        text = pretty_dir(d) if d else "Same folder as paper"
        self.out_label.setText(self.out_label.fontMetrics().elidedText(text, Qt.ElideMiddle, 168))
        self.out_label.setToolTip(str(d) if d else "")

    def set_status(self, text: str, reveal_link: bool = False):
        self.status.setText(text)
        self.reveal_btn.setVisible(reveal_link)

    # actions --------------------------------------------------------
    def choose_file(self):
        start = self.settings.value("last_open", str(Path.home()))
        f, _ = QFileDialog.getOpenFileName(self, "Open Paper", start, "PDF Documents (*.pdf)")
        if f:
            self.load(Path(f))

    def choose_folder(self):
        start = str(self.out_dir or (self.src_path.parent if self.src_path else Path.home()))
        d = QFileDialog.getExistingDirectory(self, "Save Exports To", start)
        if d:
            self.set_out_dir(Path(d))

    def load(self, path: Path):
        try:
            doc = pymupdf.open(path)
            if doc.needs_pass:
                raise ValueError("The PDF is password-protected.")
            if len(doc) == 0:
                raise ValueError("The PDF has no pages.")
        except Exception as e:
            QMessageBox.warning(self, APP, f"“{path.name}” couldn’t be opened.\n\n{e}")
            return
        if self.doc:
            self.doc.close()
        self.doc, self.src_path, self.page = doc, path, 0
        self.settings.setValue("last_open", str(path.parent))
        self.file_name.setObjectName("fileName")
        self.file_name.style().unpolish(self.file_name)
        self.file_name.style().polish(self.file_name)
        self.file_name.setText(self.file_name.fontMetrics().elidedText(path.stem, Qt.ElideMiddle, 224))
        self.file_name.setToolTip(path.name)
        n = len(doc)
        self.file_meta.setText(f"{n} page{'s' * (n != 1)}  ·  {human_size(path.stat().st_size)}")
        self.file_meta.show()
        self.set_status("")
        self.setWindowTitle(path.name if MAC else f"{path.name} — {APP}")
        if MAC:
            self.setWindowFilePath(str(path))
        self.refresh()
        self.render()

    def go(self, step: int):
        if not self.doc:
            return
        new = max(0, min(len(self.doc) - 1, self.page + step))
        if new != self.page:
            self.page = new
            self.refresh()
            self.render()

    def wheelEvent(self, e):
        if self.doc and self.canvas.underMouse():
            self._wheel = getattr(self, "_wheel", 0) + e.angleDelta().y()
            if abs(self._wheel) >= 120:
                self.go(-1 if self._wheel > 0 else 1)
                self._wheel = 0

    def render(self):
        if not self.doc:
            return
        try:
            one = build(self.doc, self.options(), [self.page])
            pr = one[0].rect
            aspect = pr.width / pr.height
            target = self.canvas.page_rect(aspect)
            zoom = max(0.2, target.width() * self.canvas.devicePixelRatioF() / pr.width)
            pix = one[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            one.close()
        except Exception as e:
            self.set_status(f"Couldn’t render page {self.page + 1}")
            self.status.setToolTip(str(e))
            return
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        self.canvas.set_page(QPixmap.fromImage(img), aspect)

    def export(self):
        if not self.doc or self.thread:
            return
        dst = default_output(self.src_path)
        if self.out_dir:
            dst = self.out_dir / dst.name
        if not dst.parent.is_dir():
            QMessageBox.warning(self, APP, f"The folder “{dst.parent}” can’t be found.")
            return
        if dst.exists():
            box = QMessageBox(QMessageBox.Warning, APP, f"“{dst.name}” already exists.", parent=self)
            box.setInformativeText("Do you want to replace it?")
            replace = box.addButton("Replace", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is not replace:
                return
        self.set_status("")
        self.thread = QThread(self)
        self.worker = Exporter(self.src_path, dst, self.options())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.export_done)
        self.worker.failed.connect(self.export_failed)
        self.refresh()
        self.thread.start()

    def _finish(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.refresh()

    def export_done(self, path: str, n: int):
        self.last_output = Path(path)
        self._finish()
        self.set_status(f"✓  Exported {n} pages", reveal_link=True)
        self.status.setToolTip(path)

    def export_failed(self, msg: str):
        self._finish()
        QMessageBox.warning(self, APP, f"The export didn’t finish.\n\n{msg}")

    def reveal_last(self):
        if self.last_output and self.last_output.exists():
            reveal(self.last_output)

    def retheme(self):
        apply_theme(QApplication.instance())
        for w in self.findChildren(QWidget):
            w.update()

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(e)


class App(QApplication):
    """Also receives files opened from Finder or dropped on the Dock icon (macOS)."""

    fileOpened = Signal(str)

    def event(self, e):
        if e.type() == QEvent.FileOpen:
            self.fileOpened.emit(e.file())
            return True
        return super().event(e)


def main() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReviewMargin.App")
        except Exception:
            pass
    app = App(sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    icon = resource("assets/icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    apply_theme(app)

    w = Window()
    try:
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: w.retheme())
    except AttributeError:
        pass
    app.fileOpened.connect(lambda f: w.load(Path(f)))
    w.show()
    for a in sys.argv[1:]:
        if a.lower().endswith(".pdf") and os.path.isfile(a):
            w.load(Path(a))
            break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
