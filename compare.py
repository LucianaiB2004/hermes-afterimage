"""Zero-token visual check: compare a recorded template around a click to a fresh capture."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageChops, ImageFilter, ImageStat

BOX = 34  # half-size of the compared region, in pixels
SEARCH = 24  # extra search radius for a slightly moved control (still 0 tokens)


@dataclass
class CompareResult:
    match: bool
    diff: float
    threshold: float
    coordinate: tuple[int, int]  # possibly adjusted
    offset: tuple[int, int] = (0, 0)


def _region(im: Image.Image, cx: int, cy: int, box: int = BOX) -> Image.Image:
    im = im.convert("RGB")
    x0, y0 = max(0, cx - box), max(0, cy - box)
    x1, y1 = min(im.width, cx + box), min(im.height, cy + box)
    pad = Image.new("RGB", (box * 2, box * 2), (0, 0, 0))
    crop = im.crop((x0, y0, x1, y1))
    pad.paste(crop, (box - (cx - x0), box - (cy - y0)))
    return pad.convert("L").filter(ImageFilter.GaussianBlur(0.6))


def _mad(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        b = b.resize(a.size, Image.BILINEAR)
    return float(ImageStat.Stat(ImageChops.difference(a, b)).mean[0])


def compare(
    recorded: Union[Image.Image, Path, str],
    current: Union[Image.Image, Path, str],
    coordinate: tuple[int, int],
    threshold: float = 12.0,
    search: int = SEARCH,
    box: int = BOX,
) -> CompareResult:
    """Compare the patch around `coordinate`. Search a small window and accept a
    nearby match (auto-adjusts the click, still 0 LLM tokens)."""
    rec = recorded if isinstance(recorded, Image.Image) else Image.open(recorded)
    cur = current if isinstance(current, Image.Image) else Image.open(current)
    rec, cur = rec.convert("RGB"), cur.convert("RGB")
    # If sizes drifted, scale current to the recorded capture size so coords still line up.
    if cur.size != rec.size and rec.width > 0:
        cur = cur.resize(rec.size, Image.BILINEAR)
    cx, cy = int(coordinate[0]), int(coordinate[1])
    expected = _region(rec, cx, cy, box)
    best = (999.0, 0, 0)
    for dy in range(-search, search + 1, 2):
        for dx in range(-search, search + 1, 2):
            d = _mad(expected, _region(cur, cx + dx, cy + dy, box))
            if d < best[0]:
                best = (d, dx, dy)
                if d < 1.0:
                    break
    # Refine 1px around the best coarse point
    bx, by = best[1], best[2]
    for dy in range(by - 1, by + 2):
        for dx in range(bx - 1, bx + 2):
            d = _mad(expected, _region(cur, cx + dx, cy + dy, box))
            if d < best[0]:
                best = (d, dx, dy)
    diff, dx, dy = best
    return CompareResult(
        match=diff < threshold,
        diff=round(diff, 2),
        threshold=threshold,
        coordinate=(cx + dx, cy + dy),
        offset=(dx, dy),
    )
