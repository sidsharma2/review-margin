#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Command-line version of Review Margin.

    review_margin.py paper.pdf                 -> paper (review).pdf, ruled notes
    review_margin.py *.pdf --style grid        -> squared notes area
    review_margin.py paper.pdf --notes 0.5     -> notes take half the width
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from margin_core import STYLES, Options, convert_file, default_output  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdfs", nargs="+", type=Path)
    p.add_argument("--notes", type=float, default=0.45, help="fraction of width for notes (default 0.45)")
    p.add_argument("--ratio", type=float, default=4 / 3, help="minimum width/height (default 4:3, iPad)")
    p.add_argument("--style", choices=STYLES, default="lines", help="notes background (default lines)")
    p.add_argument("--no-divider", action="store_true", help="no line between paper and notes")
    p.add_argument("-o", "--out-dir", type=Path, help="where to write (default: next to each input)")
    a = p.parse_args(argv)
    if not 0.05 <= a.notes <= 0.8:
        p.error("--notes must be between 0.05 and 0.8")

    opts = Options(notes=a.notes, ratio=a.ratio, style=a.style, divider=not a.no_divider)
    failed = 0
    for src in a.pdfs:
        if src.suffix.lower() != ".pdf" or not src.is_file() or src.stem.endswith("(review)"):
            print(f"skip: {src}", file=sys.stderr)
            continue
        dst = default_output(src)
        if a.out_dir:
            a.out_dir.mkdir(parents=True, exist_ok=True)
            dst = a.out_dir / dst.name
        try:
            print(f"{dst}  ({convert_file(src, dst, opts)} pages)")
        except Exception as e:
            failed += 1
            print(f"error: {src}: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
