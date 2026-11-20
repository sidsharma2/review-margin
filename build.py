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

if sys.platform == "darwin":
    # Let Finder "Open With" and the Dock icon accept PDFs.
    import plistlib
    plist = root / "dist/Review Margin.app/Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info["CFBundleDocumentTypes"] = [{
        "CFBundleTypeName": "PDF Document",
        "CFBundleTypeRole": "Viewer",
        "LSHandlerRank": "Alternate",
        "LSItemContentTypes": ["com.adobe.pdf"],
    }]
    info["NSHighResolutionCapable"] = True
    info["CFBundleShortVersionString"] = "1.0.0"
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(plist.parent.parent)], check=True)
