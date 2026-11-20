"""Build a standalone app with PyInstaller: dist/Review Margin.app (macOS) or
dist/Review Margin/Review Margin.exe (Windows)."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if not (root / "assets/icon.png").exists():
    subprocess.run([sys.executable, "make_icon.py"], cwd=root, check=True)

sep = ";" if sys.platform == "win32" else ":"
args = [
    sys.executable, "-m", "PyInstaller", "app.py",
    "--name", "Review Margin", "--windowed", "--noconfirm", "--clean",
    "--icon", "assets/icon.png",
    "--add-data", f"assets{sep}assets",
    "--exclude-module", "tkinter",
]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "com.reviewmargin.app"]
subprocess.run(args, cwd=root, check=True)
