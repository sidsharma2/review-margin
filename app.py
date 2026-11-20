"""Review Margin — desktop app.

Import a portrait paper, preview it on landscape pages with a notes area on
the right, and export the result for GoodNotes / Notability.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QKeySequence, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from margin_core import STYLES, Options, build, convert_file, default_output

APP = "Review Margin"
ACCENT = "#3b6fe0"


def resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def reveal(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)])
    else:
        subprocess.run(["xdg-open", str(path.parent)])


STYLE_SHEET = f"""
QMainWindow, #sidebar {{ background: #f6f6f4; }}
QLabel {{ color: #1f2329; font-size: 13px; }}
#title {{ font-size: 20px; font-weight: 600; }}
#subtitle, #hint {{ color: #6b7280; font-size: 12px; }}
#section {{ color: #6b7280; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
#fileCard {{ background: white; border: 1px solid #e3e3df; border-radius: 10px; }}
#fileName {{ font-weight: 600; }}
QPushButton {{
    background: white; border: 1px solid #d6d6d1; border-radius: 8px;
    padding: 7px 12px; font-size: 13px; color: #1f2329;
}}
QPushButton:hover {{ border-color: #b9b9b3; background: #fbfbfa; }}
QPushButton:disabled {{ color: #a3a3a3; background: #f1f1ef; border-color: #e3e3df; }}
QPushButton#primary {{
    background: {ACCENT}; color: white; border: none; font-weight: 600; padding: 10px;
}}
QPushButton#primary:hover {{ background: #2f5fcc; }}
QPushButton#primary:disabled {{ background: #a9bdea; color: #eef2fb; }}
QPushButton#seg {{ border-radius: 0; padding: 6px 0; margin: 0; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#segFirst {{ border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 6px 0; }}
QPushButton#segLast {{ border-top-left-radius: 0; border-bottom-left-radius: 0; padding: 6px 0; }}
QPushButton#segFirst:checked, QPushButton#segLast:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#nav {{ border: none; background: transparent; color: #e8e8e8; font-size: 18px; padding: 4px 14px; }}
QPushButton#nav:hover {{ color: white; }}
QPushButton#nav:disabled {{ color: #5d6168; background: transparent; }}
QPushButton#link {{ border: none; background: transparent; color: {ACCENT}; padding: 0; text-align: left; }}
QSlider::groove:horizontal {{ height: 4px; background: #dcdcd7; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: white; border: 1px solid #c4c4be; width: 16px; height: 16px;
    margin: -7px 0; border-radius: 8px;
}}
QCheckBox {{ font-size: 13px; color: #1f2329; }}
#previewPane {{ background: #2b2e33; }}
#pageLabel {{ color: #c9cbd0; font-size: 12px; }}
#empty {{ color: #9aa0a8; font-size: 15px; }}
"""


class Exporter(QObject):
    done = Signal(str, int)
    failed = Signal(str)

    def __init__(self, src: Path, dst: Path, opts: Options):
        super().__init__()
        self.src, self.dst, self.opts = src, dst, opts

    def run(self) -> None:
        try:
            self.done.emit(str(self.dst), convert_file(self.src, self.dst, self.opts))
        except Exception as e:  # shown to the user
            self.failed.emit(str(e))


class Preview(QLabel):
    """Scales the rendered page to fit and accepts dropped PDFs."""

    fileDropped = Signal(Path)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(300, 200)
        self._image: QImage | None = None
        self.showEmpty()

    def showEmpty(self) -> None:
        self._image = None
        self.setObjectName("empty")
        self.setStyleSheet("")
        self.setText("Drop a paper PDF here\nor use Import PDF…")

    def setImage(self, img: QImage) -> None:
        self._image = img
        self._rescale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self) -> None:
        if self._image is None:
            return
        dpr = self.devicePixelRatioF()
        avail = self.size() * dpr
        pm = QPixmap.fromImage(self._image).scaled(
            avail.width() - 48 * dpr, avail.height() - 48 * dpr,
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.setPixmap(pm)

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                self.fileDropped.emit(Path(u.toLocalFile()))
                break


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
        self.resize(1180, 760)
        self.setAcceptDrops(True)

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._sidebar())
        lay.addWidget(self._preview_pane(), 1)
        self.setCentralWidget(root)

        self.timer = QTimer(self, singleShot=True, interval=120)
        self.timer.timeout.connect(self.render)

        open_act = QAction("Import PDF…", self, shortcut=QKeySequence.Open, triggered=self.choose_file)
        save_act = QAction("Export", self, shortcut=QKeySequence.Save, triggered=self.export)
        self.addActions([open_act, save_act])
        self.menuBar().addMenu("&File").addActions([open_act, save_act])

        self.refresh_state()

    # ---------- layout ----------
    def _sidebar(self) -> QWidget:
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(300)
        v = QVBoxLayout(side)
        v.setContentsMargins(22, 24, 22, 22)
        v.setSpacing(10)

        v.addWidget(QLabel(APP, objectName="title"))
        sub = QLabel("Papers on landscape pages with room\nfor handwritten review notes.", objectName="subtitle")
        v.addWidget(sub)
        v.addSpacing(14)

        v.addWidget(QLabel("PAPER", objectName="section"))
        card = QFrame(objectName="fileCard")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        self.file_name = QLabel("No file yet", objectName="fileName")
        self.file_name.setWordWrap(True)
        self.file_meta = QLabel("Import or drop a PDF", objectName="hint")
        cv.addWidget(self.file_name)
        cv.addWidget(self.file_meta)
        v.addWidget(card)
        imp = QPushButton("Import PDF…")
        imp.clicked.connect(self.choose_file)
        v.addWidget(imp)
        v.addSpacing(14)

        v.addWidget(QLabel("NOTES AREA", objectName="section"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Width"))
        row.addStretch()
        self.width_label = QLabel("", objectName="hint")
        row.addWidget(self.width_label)
        v.addLayout(row)
        self.slider = QSlider(Qt.Horizontal, minimum=20, maximum=60, singleStep=1, pageStep=5)
        self.slider.setValue(int(self.settings.value("notes", 45)))
        self.slider.valueChanged.connect(self.options_changed)
        v.addWidget(self.slider)

        v.addSpacing(4)
        v.addWidget(QLabel("Background"))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.style_group = QButtonGroup(self)
        current = self.settings.value("style", "lines")
        for i, s in enumerate(STYLES):
            b = QPushButton(s.capitalize(), checkable=True)
            b.setObjectName("segFirst" if i == 0 else "segLast" if i == len(STYLES) - 1 else "seg")
            b.setChecked(s == current)
            self.style_group.addButton(b, i)
            seg.addWidget(b)
        self.style_group.idClicked.connect(self.options_changed)
        v.addLayout(seg)

        self.divider = QCheckBox("Line between paper and notes")
        self.divider.setChecked(self.settings.value("divider", "true") in (True, "true"))
        self.divider.toggled.connect(self.options_changed)
        v.addWidget(self.divider)

        v.addStretch()

        v.addWidget(QLabel("SAVE TO", objectName="section"))
        self.out_label = QLabel("Same folder as the paper", objectName="hint")
        self.out_label.setWordWrap(True)
        v.addWidget(self.out_label)
        orow = QHBoxLayout()
        chg = QPushButton("Choose folder…")
        chg.clicked.connect(self.choose_folder)
        self.same_btn = QPushButton("Reset")
        self.same_btn.clicked.connect(lambda: self.set_out_dir(None))
        orow.addWidget(chg)
        orow.addWidget(self.same_btn)
        v.addLayout(orow)
        saved = self.settings.value("out_dir", "")
        self.set_out_dir(Path(saved) if saved and Path(saved).is_dir() else None)

        v.addSpacing(8)
        self.export_btn = QPushButton("Export PDF", objectName="primary")
        self.export_btn.clicked.connect(self.export)
        v.addWidget(self.export_btn)
        self.status = QLabel("", objectName="hint")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.reveal_btn = QPushButton("Show in Finder" if sys.platform == "darwin" else "Show in folder",
                                      objectName="link")
        self.reveal_btn.clicked.connect(lambda: self.last_output and reveal(self.last_output))
        self.reveal_btn.hide()
        v.addWidget(self.reveal_btn)
        return side

    def _preview_pane(self) -> QWidget:
        pane = QFrame(objectName="previewPane")
        v = QVBoxLayout(pane)
        v.setContentsMargins(0, 0, 0, 10)
        self.preview = Preview()
        self.preview.fileDropped.connect(self.load)
        v.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        nav.addStretch()
        self.prev_btn = QPushButton("‹", objectName="nav", clicked=lambda: self.go(-1))
        self.page_label = QLabel("", objectName="pageLabel")
        self.next_btn = QPushButton("›", objectName="nav", clicked=lambda: self.go(1))
        for w in (self.prev_btn, self.page_label, self.next_btn):
            nav.addWidget(w)
        nav.addStretch()
        v.addLayout(nav)
        return pane

    # ---------- state ----------
    def options(self) -> Options:
        return Options(notes=self.slider.value() / 100,
                       style=STYLES[self.style_group.checkedId()],
                       divider=self.divider.isChecked())

    def options_changed(self, *_):
        o = self.options()
        self.width_label.setText(f"{self.slider.value()}%")
        self.settings.setValue("notes", self.slider.value())
        self.settings.setValue("style", o.style)
        self.settings.setValue("divider", "true" if o.divider else "false")
        self.timer.start()

    def refresh_state(self):
        has = self.doc is not None
        n = len(self.doc) if has else 0
        self.export_btn.setEnabled(has and self.thread is None)
        self.prev_btn.setEnabled(has and self.page > 0)
        self.next_btn.setEnabled(has and self.page < n - 1)
        self.page_label.setText(f"Page {self.page + 1} of {n}" if has else "")
        self.width_label.setText(f"{self.slider.value()}%")

    def set_out_dir(self, d: Path | None):
        self.out_dir = d
        self.settings.setValue("out_dir", str(d) if d else "")
        if d:
            home = str(Path.home())
            shown = "~" + str(d)[len(home):] if str(d).startswith(home) else str(d)
            self.out_label.setText(shown)
            self.out_label.setToolTip(str(d))
        else:
            self.out_label.setText("Same folder as the paper")
        self.same_btn.setVisible(d is not None)

    # ---------- actions ----------
    def choose_file(self):
        start = self.settings.value("last_open", str(Path.home()))
        f, _ = QFileDialog.getOpenFileName(self, "Import a paper", start, "PDF files (*.pdf)")
        if f:
            self.load(Path(f))

    def choose_folder(self):
        start = str(self.out_dir or (self.src_path.parent if self.src_path else Path.home()))
        d = QFileDialog.getExistingDirectory(self, "Save exported PDFs to", start)
        if d:
            self.set_out_dir(Path(d))

    def load(self, path: Path):
        try:
            doc = pymupdf.open(path)
            if doc.needs_pass:
                raise ValueError("this PDF is password-protected")
            if len(doc) == 0:
                raise ValueError("this PDF has no pages")
        except Exception as e:
            QMessageBox.warning(self, APP, f"Couldn't open {path.name}:\n{e}")
            return
        if self.doc:
            self.doc.close()
        self.doc, self.src_path, self.page = doc, path, 0
        self.settings.setValue("last_open", str(path.parent))
        self.file_name.setText(path.name)
        self.file_meta.setText(f"{len(doc)} page{'s' * (len(doc) != 1)}")
        self.status.setText("")
        self.reveal_btn.hide()
        self.setWindowTitle(f"{path.name} — {APP}")
        self.refresh_state()
        self.render()

    def go(self, step: int):
        if self.doc:
            self.page = max(0, min(len(self.doc) - 1, self.page + step))
            self.refresh_state()
            self.render()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp):
            self.go(-1)
        elif e.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Space):
            self.go(1)
        else:
            super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        self.preview.dragEnterEvent(e)

    def dropEvent(self, e):
        self.preview.dropEvent(e)

    def render(self):
        if not self.doc:
            return
        try:
            one = build(self.doc, self.options(), [self.page])
            pix = one[0].get_pixmap(dpi=144, alpha=False)
            one.close()
        except Exception as e:
            self.preview.setText(f"Couldn't render this page:\n{e}")
            return
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        self.preview.setImage(img)

    def export(self):
        if not self.doc or self.thread:
            return
        dst = default_output(self.src_path)
        if self.out_dir:
            dst = self.out_dir / dst.name
        if dst.exists():
            r = QMessageBox.question(self, APP, f"“{dst.name}” already exists in that folder.\nReplace it?")
            if r != QMessageBox.Yes:
                return
        self.status.setText("Exporting…")
        self.reveal_btn.hide()
        self.thread = QThread(self)
        self.worker = Exporter(self.src_path, dst, self.options())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.export_done)
        self.worker.failed.connect(self.export_failed)
        self.refresh_state()
        self.thread.start()

    def _finish_thread(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.refresh_state()

    def export_done(self, path: str, n: int):
        self._finish_thread()
        self.last_output = Path(path)
        self.status.setText(f"Saved {n} pages as “{self.last_output.name}”")
        self.reveal_btn.show()

    def export_failed(self, msg: str):
        self._finish_thread()
        self.status.setText("")
        QMessageBox.warning(self, APP, f"Export failed:\n{msg}")


def app_icon() -> QIcon:
    p = resource("assets/icon.png")
    return QIcon(str(p)) if p.exists() else QIcon()


def main() -> int:
    if sys.platform == "win32":  # own taskbar icon instead of python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReviewMargin.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    # Always light, so dialogs stay readable when the OS is in dark mode.
    pal = app.style().standardPalette()
    for role, color in ((QPalette.Window, "#f6f6f4"), (QPalette.Base, "#ffffff"),
                        (QPalette.Text, "#1f2329"), (QPalette.WindowText, "#1f2329"),
                        (QPalette.ButtonText, "#1f2329"), (QPalette.Button, "#ffffff"),
                        (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#ffffff")):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(STYLE_SHEET)
    app.setWindowIcon(app_icon())
    w = Window()
    w.show()
    # a PDF passed on the command line (or "Open with…" on Windows)
    for a in sys.argv[1:]:
        if a.lower().endswith(".pdf") and os.path.isfile(a):
            w.load(Path(a))
            break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
