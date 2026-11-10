"""Direction B · Double Exposure HUD, rendered to a fullscreen ARGB layer.

Drawn at 2× and scaled down so thin brackets and mono type stay sharp on X11.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import os


def _find_font(*names: str) -> Optional[Path]:
    """Look for a font file by name in common font directories (no network)."""
    dirs = [os.environ.get("AFTERIMAGE_FONT_DIR", ""), str(Path.home() / ".local/share/fonts"),
            str(Path.home() / ".fonts"), "/usr/share/fonts", "/usr/local/share/fonts"]
    for d in dirs:
        if not d or not Path(d).is_dir():
            continue
        for n in names:
            for hit in Path(d).rglob(n):
                return hit
    return None


INTER = _find_font("Inter-VariableFont_opsz,wght.ttf", "Inter*.ttf", "DejaVuSans.ttf")
GROT = _find_font("SpaceGrotesk-VariableFont_wght.ttf", "SpaceGrotesk*.ttf", "DejaVuSans-Bold.ttf") or INTER
MONO = _find_font("JetBrainsMono-VariableFont_wght.ttf", "JetBrainsMono*.ttf", "DejaVuSansMono.ttf") or INTER

S = 2
GLASS = (14, 14, 22)
CYAN = (34, 211, 238)
MAGENTA = (232, 72, 199)
MINT = (34, 197, 94)
VIOLET = (124, 58, 237)
RED = (239, 68, 68)
INK = (17, 24, 39)


def s(v: float) -> int:
    return int(round(v * S))


def P(pts):
    return [(s(x), s(y)) for x, y in pts]


def font(path: Optional[Path], size: float, wght: Optional[int] = None, opsz: Optional[int] = None) -> ImageFont.FreeTypeFont:
    if path is None:
        return ImageFont.load_default(int(size * S))
    f = ImageFont.truetype(str(path), int(size * S))
    try:
        axes = f.get_variation_axes()
        vals = []
        for a in axes:
            n = a.get("name", b"")
            n = n.decode() if isinstance(n, bytes) else n
            low = n.lower()
            if low.startswith("weight") and wght:
                vals.append(wght)
            elif low.startswith("optical") and opsz:
                vals.append(opsz)
            else:
                vals.append(a.get("default", a["minimum"]))
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def tw(d: ImageDraw.ImageDraw, text: str, f) -> tuple[float, float]:
    b = d.textbbox((0, 0), text, font=f)
    return (b[2] - b[0]) / S, (b[3] - b[1]) / S


def ellipsize(d, t, f, max_w: float) -> str:
    """Fit one line of text into max_w (1× pixels), appending an ellipsis if needed."""
    t = (t or "").replace("\n", " ").strip()
    if max_w <= 0:
        return ""
    if tw(d, t, f)[0] <= max_w:
        return t
    ell = "…"
    if tw(d, ell, f)[0] > max_w:
        return ""
    lo, hi, best = 0, len(t), ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = t[:mid].rstrip() + ell
        if tw(d, cand, f)[0] <= max_w:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def clamp_box(x0, y0, x1, y1, W, H, pad=12):
    w, h = x1 - x0, y1 - y0
    if w > W - 2 * pad:
        x0, x1 = pad, W - pad
    else:
        if x0 < pad:
            x1 += pad - x0
            x0 = pad
        if x1 > W - pad:
            x0 -= x1 - (W - pad)
            x1 = W - pad
    if h > H - 2 * pad:
        y0, y1 = pad, H - pad
    else:
        if y0 < pad:
            y1 += pad - y0
            y0 = pad
        if y1 > H - pad:
            y0 -= y1 - (H - pad)
            y1 = H - pad
    return x0, y0, x1, y1


def text(d, xy, t, f, fill, anchor="la"):
    d.text((s(xy[0]), s(xy[1])), t, font=f, fill=fill, anchor=anchor)


def stroke(d, pts, fill, width):
    pp = P(pts)
    d.line(pp, fill=fill, width=s(width), joint="curve")
    r = s(width) / 2
    for p in (pp[0], pp[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def cursor_poly(x, y, k=1.0):
    pts = [(0, 0), (0, 22), (5.6, 17), (9.6, 26), (13.4, 24.4), (9.6, 15.6), (17, 15.6)]
    return [(x + px * k, y + py * k) for px, py in pts]


def ghost_mascot(layer, x, y, size, body, ink=INK, seed=8, eyes="open"):
    """Hand-drawn flat ghost: wobbly dome, wavy hem, two dot eyes. Not anime, not photoreal."""
    import random

    d = ImageDraw.Draw(layer, "RGBA")
    rnd = random.Random(seed)
    pts = []
    w, h = size, size * 1.12
    for i in range(60):
        t = math.pi + math.pi * i / 59
        pts.append((x + w / 2 + w / 2 * math.cos(t) + rnd.uniform(-0.25, 0.25),
                    y + w / 2 + w / 2 * math.sin(t) + rnd.uniform(-0.25, 0.25)))
    for i in range(40):
        u = i / 39
        xx = x + w - u * w
        yy = y + h - 2.0 * (1 + math.sin(u * math.pi * 6)) * size / 28
        pts.append((xx, yy))
    pts.append(pts[0])
    d.polygon(P(pts), fill=body)
    stroke(d, pts, ink, max(1.4, size / 16))
    ey = y + w * 0.48
    r = size / 18
    for ex in (x + w * 0.36, x + w * 0.62):
        if eyes == "open":
            d.ellipse([s(ex - r), s(ey - r * 1.3), s(ex + r), s(ey + r * 1.3)], fill=ink)
        else:
            d.arc([s(ex - r * 1.6), s(ey - r), s(ex + r * 1.6), s(ey + r * 1.6)],
                  200, 340, fill=ink, width=s(max(1.2, size / 20)))


def brackets(d, box, col, width, arm=14, a=255):
    x0, y0, x1, y1 = box
    for ax, ay, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        d.line(P([(ax, ay + dy * arm), (ax, ay), (ax + dx * arm, ay)]),
               fill=col + (a,), width=s(width), joint="curve")


def shadow(layer, box, radius, blur, alpha, offset=(0, 8)):
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    x0, y0, x1, y1 = box
    d.rounded_rectangle(
        [s(x0 + offset[0]), s(y0 + offset[1]), s(x1 + offset[0]), s(y1 + offset[1])],
        s(radius), fill=(15, 23, 42, alpha),
    )
    layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(s(blur))))


def glass_panel(layer, bg: Optional[Image.Image], box, r, tint=GLASS, alpha=222):
    x0, y0, x1, y1 = box
    w, h = s(x1 - x0), s(y1 - y0)
    if bg is not None:
        # bg is 1× screen RGB
        crop = bg.crop((int(x0), int(y0), int(x1), int(y1))).filter(ImageFilter.GaussianBlur(14)).convert("RGBA")
        crop = crop.resize((w, h), Image.LANCZOS)
        crop.alpha_composite(Image.new("RGBA", crop.size, tint + (alpha,)))
    else:
        crop = Image.new("RGBA", (w, h), tint + (alpha,))
    m = Image.new("L", crop.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, crop.size[0] - 1, crop.size[1] - 1], s(r), fill=255)
    layer.paste(crop, (s(x0), s(y0)), m)
    ImageDraw.Draw(layer, "RGBA").rounded_rectangle(
        [s(x0), s(y0), s(x1), s(y1)], s(r), outline=(255, 255, 255, 34), width=s(1)
    )


@dataclass
class StepView:
    title: str
    expect: str
    status: str = "pending"  # pending | current | done | bad


@dataclass
class HudState:
    mode: str = "replay"  # replay | repair
    tokens: int = 0
    flow_name: str = "Untitled flow"
    steps: list[StepView] = field(default_factory=list)
    current: int = 0
    target: Optional[tuple[int, int, int, int]] = None  # screen-absolute x0,y0,x1,y1
    candidate: Optional[tuple[int, int, int, int]] = None
    candidate_label: str = ""
    match: bool = True
    tag: str = ""
    screen: tuple[int, int] = (1920, 1200)


def render(state: HudState, background: Optional[Image.Image] = None) -> Image.Image:
    """Return a fullscreen RGBA overlay (transparent where the desktop should show)."""
    W, H = state.screen
    layer = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")
    col = MINT if (state.match and state.mode == "replay") else RED
    mcol = MINT if state.mode == "replay" else VIOLET

    if state.target:
        x0, y0, x1, y1 = state.target
        box = (x0 - 9, y0 - 9, x1 + 9, y1 + 9)
        glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow, "RGBA")
        gd.rounded_rectangle([s(box[0]), s(box[1]), s(box[2]), s(box[3])], s(10),
                             outline=col + (170,), width=s(5))
        layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s(7))))
        d = ImageDraw.Draw(layer, "RGBA")
        d.rounded_rectangle([s(box[0]), s(box[1]), s(box[2]), s(box[3])], s(10), fill=col + (26,))
        brackets(d, tuple(v + o for v, o in zip(box, (-3, -2, -3, -2))), CYAN, 2.4, a=150)
        brackets(d, tuple(v + o for v, o in zip(box, (3, 2, 3, 2))), MAGENTA, 2.4, a=150)
        brackets(d, box, (255, 255, 255) if state.match else col, 3)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        tip = (cx + 4, cy + 3)
        d.polygon(P(cursor_poly(tip[0] - 7, tip[1] + 4, 1.05)), fill=CYAN + (120,))
        d.polygon(P(cursor_poly(tip[0] + 6, tip[1] - 3, 1.05)), fill=MAGENTA + (120,))
        d.polygon(P(cursor_poly(*tip, 1.05)), fill=(255, 255, 255))
        stroke(d, cursor_poly(*tip, 1.05) + [tip], GLASS, 1.4)
        raw = state.tag
        if not raw:
            if not state.match:
                raw = f"{state.current + 1:02d}  TARGET MISSING"
            elif state.steps:
                raw = f"{state.current + 1:02d}  {state.steps[state.current].title}"
            else:
                raw = f"{state.current + 1:02d}  CLICK"
        tf = font(MONO, 12, wght=600)
        tag = ellipsize(d, raw, tf, min(260, W - 52))
        w_, _ = tw(d, tag, tf)
        tag_h = 28
        tx1 = x1 + 9
        tx0 = tx1 - w_ - 26
        ty0 = y0 - 46
        if ty0 < 12:
            ty0 = y1 + 14
        tx0, ty0, tx1, ty1 = clamp_box(tx0, ty0, tx0 + w_ + 26, ty0 + tag_h, W, H, pad=12)
        glass_panel(layer, background, (tx0, ty0, tx1, ty1), 8, alpha=230)
        d = ImageDraw.Draw(layer, "RGBA")
        d.ellipse([s(tx0 + 9), s(ty0 + 11), s(tx0 + 15), s(ty0 + 17)], fill=col)
        text(d, (tx0 + 21, ty0 + 7.5), tag, tf, (240, 240, 245))

    if state.candidate and not state.match:
        bx0, by0, bx1, by1 = state.candidate
        b2 = (bx0 - 8, by0 - 8, bx1 + 8, by1 + 8)
        d.rounded_rectangle([s(b2[0]), s(b2[1]), s(b2[2]), s(b2[3])], s(10),
                            fill=VIOLET + (30,), outline=VIOLET + (220,), width=s(2))
        if state.target:
            box = state.target
            src = (box[0] - 4, box[3] + 10)
            dst = (b2[2], b2[3] + 10)
            for i in range(9):
                t = i / 8
                px = src[0] + (dst[0] - src[0]) * t
                py = src[1] + (dst[1] - src[1]) * t + math.sin(t * math.pi) * 18
                r = 2.2
                d.ellipse([s(px - r), s(py - r), s(px + r), s(py + r)],
                          fill=VIOLET + (90 + int(150 * t),))
        if state.candidate_label:
            tf2 = font(MONO, 11.5, wght=600)
            t2 = ellipsize(d, state.candidate_label, tf2, min(280, W - 40))
            w2, _ = tw(d, t2, tf2)
            gx0, gy0 = b2[0], b2[3] + 34
            gx0, gy0, gx1, gy1 = clamp_box(gx0, gy0, gx0 + w2 + 22, gy0 + 26, W, H, pad=12)
            glass_panel(layer, background, (gx0, gy0, gx1, gy1), 8, alpha=230)
            d = ImageDraw.Draw(layer, "RGBA")
            text(d, (gx0 + 11, gy0 + 6.5), t2, tf2, (221, 214, 254))

    # Bottom dock — width follows step count; every step is shown; labels ellipsize.
    n_steps = max(len(state.steps), 1)
    brand_w, meter_w, gap, side = 250, 196, 8, 40
    chip_min, chip_pref = 148, 220
    n_show = min(n_steps, 5)
    need = brand_w + meter_w + n_show * chip_pref + gap * (n_show + 1)
    dw = min(max(980, need), W - side * 2)
    dh = 92
    dx0 = (W - dw) / 2
    dy0 = H - 24 - dh - 22
    # Keep the dock above a typical 22–32px desktop panel and fully on-screen.
    if dy0 + dh > H - 16:
        dy0 = H - 16 - dh
    if dx0 < side:
        dx0 = side
        dw = W - side * 2
    shadow(layer, (dx0, dy0, dx0 + dw, dy0 + dh), 22, 22, 120, (0, 12))
    glass_panel(layer, background, (dx0, dy0, dx0 + dw, dy0 + dh), 22, alpha=230)
    d = ImageDraw.Draw(layer, "RGBA")
    ghost_mascot(layer, dx0 + 22, dy0 + 22, 38, (245, 245, 250), ink=(40, 40, 52),
                 eyes="open" if state.match else "focus")
    d = ImageDraw.Draw(layer, "RGBA")
    text(d, (dx0 + 72, dy0 + 25), "afterimage", font(GROT, 19, wght=700), (245, 245, 250))
    ff = font(INTER, 12, wght=450)
    suffix = f" · {n_steps} steps"
    maxw = brand_w - 90
    if tw(d, state.flow_name + suffix, ff)[0] <= maxw:
        flow_line = state.flow_name + suffix
    else:
        flow_line = ellipsize(d, state.flow_name, ff, maxw)
    text(d, (dx0 + 73, dy0 + 51), flow_line, ff, (156, 156, 170))
    split_x = dx0 + brand_w
    d.line(P([(split_x, dy0 + 20), (split_x, dy0 + dh - 20)]), fill=(255, 255, 255, 30), width=s(1))

    steps = state.steps or [StepView("Click “Export”", "Save dialog opens", "current"),
                            StepView("Click “Save”", "→ “Saved”", "pending")]
    steps = steps[:n_show]
    mx0 = dx0 + dw - meter_w
    inner_left = split_x + 16
    inner_right = mx0 - 16
    avail = max(chip_min, inner_right - inner_left)
    cwid = (avail - gap * (len(steps) - 1)) / len(steps) if steps else avail
    title_f = font(INTER, 14 if len(steps) >= 3 else 15.5, wght=650)
    sub_f = font(INTER, 11 if len(steps) >= 3 else 12, wght=450)
    num_f = font(MONO, 13, wght=700)
    for i, st in enumerate(steps):
        cx0 = inner_left + i * (cwid + gap)
        cy0, cy1 = dy0 + 14, dy0 + dh - 14
        is_cur = (i == state.current)
        step_col = RED if (is_cur and not state.match) else (MINT if is_cur else (120, 120, 135))
        if is_cur:
            d.rounded_rectangle([s(cx0), s(cy0), s(cx0 + cwid), s(cy1)], s(14),
                                fill=step_col + (34,), outline=step_col + (150,), width=s(1))
        else:
            d.rounded_rectangle([s(cx0), s(cy0), s(cx0 + cwid), s(cy1)], s(14),
                                outline=(255, 255, 255, 36), width=s(1))
        nc = step_col if is_cur else (120, 120, 135)
        text(d, (cx0 + 12, cy0 + 13), f"{i+1:02d}", num_f, nc)
        mark_room = 28 if is_cur else 10
        title_max = cwid - 42 - mark_room
        title_fill = (245, 245, 250) if is_cur else (170, 170, 185)
        title = ellipsize(d, st.title, title_f, title_max)
        text(d, (cx0 + 40, cy0 + 11), title, title_f, title_fill)
        if is_cur and not state.match:
            sub = st.expect if ("differ" in (st.expect or "").lower() or "Δ" in (st.expect or "")) else "pixels differ"
        else:
            sub = ("expect · " + st.expect) if st.expect else ""
        sub = ellipsize(d, sub, sub_f, title_max)
        text(d, (cx0 + 40, cy0 + 36), sub, sub_f, (190, 190, 205) if is_cur else (120, 120, 135))
        if is_cur:
            mark = "✓" if state.match else "!"
            mx, my = cx0 + cwid - 16, cy0 + 32
            d.ellipse([s(mx - 11), s(my - 11), s(mx + 11), s(my + 11)], fill=step_col)
            mf = font(INTER, 13, wght=800)
            text(d, (mx, my + 0.5), mark, mf, GLASS, "mm")

    d.line(P([(mx0 - 12, dy0 + 20), (mx0 - 12, dy0 + dh - 20)]), fill=(255, 255, 255, 30), width=s(1))
    lab = "REPLAY" if state.mode == "replay" else "AI · REPAIRING"
    text(d, (mx0, dy0 + 18), lab, font(MONO, 11, wght=700), mcol)
    num = f"{state.tokens:06d}"
    nf = font(MONO, 24, wght=700)
    stripped = num.lstrip("0")
    lead = 6 - len(stripped) if stripped else 5
    xx = mx0
    zero_w = tw(d, "0", nf)[0]
    for i, ch in enumerate(num):
        c = (90, 90, 105) if i < lead else (245, 245, 250)
        text(d, (xx, dy0 + 36), ch, nf, c)
        xx += zero_w + 1.5
    tok_label = "tok"
    # Keep "tok" inside the meter column.
    tok_x = min(xx + 6, mx0 + meter_w - 8 - tw(d, tok_label, font(MONO, 12, wght=500))[0])
    text(d, (tok_x, dy0 + 48), tok_label, font(MONO, 12, wght=500), (156, 156, 170))
    by = dy0 + dh - 18
    bar_w = meter_w - 26
    d.rounded_rectangle([s(mx0), s(by), s(mx0 + bar_w), s(by + 4)], s(2), fill=(255, 255, 255, 30))
    if state.mode == "repair":
        frac = min(1.0, state.tokens / 4000)
        d.rounded_rectangle([s(mx0), s(by), s(mx0 + bar_w * max(frac, 0.08)), s(by + 4)], s(2), fill=VIOLET)
    else:
        d.ellipse([s(mx0 - 2), s(by - 1), s(mx0 + 6), s(by + 5)], fill=MINT)

    return layer.resize((W, H), Image.LANCZOS)

