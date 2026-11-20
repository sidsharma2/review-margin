"""Shared conversion logic: put each portrait page on the left of a landscape
page and leave the right side free for handwritten notes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

STYLES = ("blank", "lines", "grid", "dots")
GRAY = (0.82, 0.82, 0.82)


@dataclass
class Options:
    notes: float = 0.45        # fraction of the output width kept for notes
    ratio: float = 4 / 3       # minimum width/height (4:3 fills an iPad)
    style: str = "lines"       # one of STYLES
    divider: bool = True       # thin line between paper and notes
    spacing: float = 24        # line / grid spacing in points


def _draw_notes(page: pymupdf.Page, x0: float, W: float, H: float, o: Options) -> None:
    pad = 18
    if o.divider:
        page.draw_line((x0, 0), (x0, H), color=GRAY, width=0.6)
    if o.style == "lines":
        y = pad + o.spacing
        while y < H - pad:
            page.draw_line((x0 + pad, y), (W - pad, y), color=GRAY, width=0.4)
            y += o.spacing
    elif o.style in ("grid", "dots"):
        step = o.spacing * 0.75
        xs = [x0 + pad + i * step for i in range(int((W - x0 - 2 * pad) // step) + 1)]
        ys = [pad + j * step for j in range(int((H - 2 * pad) // step) + 1)]
        if not xs or not ys:
            return
        shape = page.new_shape()
        if o.style == "grid":
            for x in xs:
                shape.draw_line((x, ys[0]), (x, ys[-1]))
            for y in ys:
                shape.draw_line((xs[0], y), (xs[-1], y))
            shape.finish(color=GRAY, width=0.3)
        else:
            for x in xs:
                for y in ys:
                    shape.draw_circle((x, y), 0.6)
            shape.finish(color=GRAY, fill=GRAY)
        shape.commit()


def build(src: pymupdf.Document, o: Options, pages: list[int] | None = None) -> pymupdf.Document:
    """Return a new document with the margin layout applied (all pages, or just `pages`)."""
    if not 0.05 <= o.notes <= 0.8:
        raise ValueError("notes must be between 0.05 and 0.8")
    out = pymupdf.open()
    for n in (pages if pages is not None else range(len(src))):
        r = src[n].rect
        H = r.height
        W = max(r.width / (1 - o.notes), H * o.ratio)
        new = out.new_page(width=W, height=H)
        new.show_pdf_page(pymupdf.Rect(0, 0, r.width, H), src, n)
        _draw_notes(new, r.width, W, H, o)
    return out


def default_output(src: Path) -> Path:
    return src.with_name(f"{src.stem} (review).pdf")


def convert_file(src: Path, dst: Path, o: Options) -> int:
    with pymupdf.open(src) as doc:
        out = build(doc, o)
        try:
            out.set_toc(doc.get_toc())
        except Exception:
            pass  # a broken outline shouldn't stop the export
        meta = dict(doc.metadata or {})
        meta["title"] = (meta.get("title") or src.stem) + " (review)"
        out.set_metadata(meta)
        out.save(dst, garbage=3, deflate=True)
        n = len(out)
        out.close()
    return n
