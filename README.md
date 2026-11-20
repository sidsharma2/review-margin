# Review Margin

A small desktop app (macOS and Windows) for reviewing papers by hand. It puts
each portrait page of a PDF on the left of a landscape page and leaves the
right side free for handwritten comments. Open the result in GoodNotes,
Notability or any other annotation app.

- **Open** a PDF (⌘O / Ctrl+O, drag it onto the window, or onto the Dock icon on Mac)
- **Preview** each page live; ← → or scroll to flip pages
- Follows the system light / dark appearance
- **Adjust** notes width (20–60%), background (blank, lines, grid, dots), divider line
- **Save to** the paper's folder or any folder you pick, then **Export PDF** (⌘E / Ctrl+E)
  (`<name> (review).pdf`)

The paper is placed as vector content, so text stays sharp, searchable and
selectable. Output pages are at least 4:3, so they fill an iPad in landscape.

## Download

Each push to `main` builds both apps in GitHub Actions (**Actions → Build
apps → Artifacts**). Pushing a tag like `v1.0.0` also attaches them to a Release.

The apps aren't code-signed, so the first launch needs one extra step:
- **macOS:** right-click *Review Margin.app* → **Open** → **Open**.
- **Windows:** on the SmartScreen prompt, **More info** → **Run anyway**.

## Run from source

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py

Build a standalone app for the current OS: `pip install pyinstaller pillow && python build.py`.

## Command line

    ./review_margin.py paper.pdf                  # ruled notes (needs uv)
    ./review_margin.py *.pdf --style grid --notes 0.5 -o ~/Desktop/review

## Files

- `margin_core.py`: the conversion (PyMuPDF)
- `app.py`: the Qt (PySide6) app
- `review_margin.py`: CLI
- `build.py`, `make_icon.py`: packaging and icon
