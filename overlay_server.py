"""Direction B live overlay: a 32-bit ARGB, always-on-top, click-through X11 window.

Talks JSON lines over a Unix socket (one request, one response). Commands:
  {"op":"show","state":{...HudState...}}
  {"op":"hide"}
  {"op":"quit"}
"""
from __future__ import annotations

import json
import os
import select
import socket
import sys
import tempfile
from pathlib import Path

# Allow running as `python overlay_server.py` with the plugin dir on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_SOCK = os.environ.get(
    "AFTERIMAGE_SOCK",
    str(Path(tempfile.gettempdir()) / "afterimage-overlay.sock"),
)


def _alpha_rects(im, min_alpha=24, pad=24):
    """A few padded bounding boxes of visible pixels.

    Per-row micro-rects explode past 200 on Gaussian-blur halos and the old
    fallback then unioned only the *first* 200 (clipping the dock). Band the
    rows instead: typically one box around the target and one around the dock.
    """
    a = im.split()[-1]
    w, h = im.size
    raw = a.tobytes()
    bands = []
    for y in range(h):
        off = y * w
        x0 = x1 = None
        row = raw[off:off + w]
        # skip empty rows quickly
        if max(row) < min_alpha:
            continue
        for x, val in enumerate(row):
            if val >= min_alpha:
                if x0 is None:
                    x0 = x
                x1 = x + 1
        if x0 is not None:
            bands.append((y, x0, x1))
    if not bands:
        return [(0, 0, 1, 1)]
    groups = []
    y0, xa, xb, prev = bands[0][0], bands[0][1], bands[0][2], bands[0][0]
    for y, x0, x1 in bands[1:]:
        if y <= prev + pad + 2:
            xa = min(xa, x0)
            xb = max(xb, x1)
            prev = y
        else:
            groups.append((y0, prev + 1, xa, xb))
            y0, xa, xb, prev = y, x0, x1, y
    groups.append((y0, prev + 1, xa, xb))
    rects = []
    for y0, y1, x0, x1 in groups:
        x0p = max(0, x0 - pad)
        y0p = max(0, y0 - pad)
        x1p = min(w, x1 + pad)
        y1p = min(h, y1 + pad)
        rects.append((x0p, y0p, max(1, x1p - x0p), max(1, y1p - y0p)))
    return rects


def _put_image(win, gc, im, X, apply_shape=False):
    """Tile PutImage because the request length field is 16-bit."""
    w, h = im.size
    rows = max(1, min(h, 60000 // max(4, w * 4)))
    for y in range(0, h, rows):
        hh = min(rows, h - y)
        tile = im.crop((0, y, w, y + hh))
        win.put_image(gc, 0, y, w, hh, X.ZPixmap, 32, 0, tile.tobytes("raw", "BGRA"))
    if apply_shape:
        from Xlib.ext import shape as _shape
        rects = _alpha_rects(im)
        shaped = [{"x": x, "y": y, "width": ww, "height": hh} for x, y, ww, hh in rects]
        win.shape_rectangles(_shape.SO.Set, _shape.SK.Bounding, 0, 0, 0, shaped)
        # keep click-through
        win.shape_rectangles(_shape.SO.Set, _shape.SK.Input, 0, 0, 0, [])
        print(f"afterimage-overlay shape rects={len(shaped)} first={shaped[:3]}", flush=True)


def run(sock_path: str = DEFAULT_SOCK, display=None):
    from Xlib import X, display as xdisplay
    from Xlib.ext import shape
    from PIL import Image

    from overlay_draw import HudState, StepView, render

    if display:
        os.environ["DISPLAY"] = display
    elif "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":6"

    d = xdisplay.Display()
    scr = d.screen()
    vis = next(v for depth in scr.allowed_depths if depth.depth == 32
               for v in depth.visuals if v.visual_class == 4)
    cmap = scr.root.create_colormap(vis.visual_id, X.AllocNone)
    sw = scr.width_in_pixels
    sh = scr.height_in_pixels
    # background_pixmap=0 (None): do not auto-fill on Map/Expose, otherwise
    # MapWindow after PutImage would wipe the ARGB buffer to fully transparent.
    win = scr.root.create_window(
        0, 0, sw, sh, 0, 32, X.InputOutput, vis.visual_id,
        colormap=cmap, border_pixel=0, override_redirect=1,
        background_pixmap=0,
        event_mask=X.ExposureMask,
    )
    win.shape_rectangles(shape.SO.Set, shape.SK.Input, 0, 0, 0, [])
    try:
        bypass = d.intern_atom("_NET_WM_BYPASS_COMPOSITOR")
        card = d.intern_atom("CARDINAL")
        # 2 = force compositing so a screen-sized ARGB window keeps per-pixel alpha
        win.change_property(bypass, card, 32, [2])
    except Exception:
        pass
    gc = win.create_gc()
    mapped = False
    last = None

    def paint(rgba: Image.Image, apply_shape: bool = True):
        nonlocal mapped, last
        if rgba.size != (sw, sh):
            rgba = rgba.resize((sw, sh), Image.LANCZOS)
        last = rgba
        # Map first (empty, no background fill), then upload pixels so Map/Expose
        # cannot wipe the buffer.
        if not mapped:
            win.map()
            mapped = True
            d.sync()
        _put_image(win, gc, rgba, X, apply_shape=apply_shape)
        try:
            rgba.save("/tmp/afterimage-hud-last.png")
        except Exception:
            pass
        win.configure(stack_mode=X.Above)
        d.sync()

    def hide():
        nonlocal mapped
        if mapped:
            win.unmap()
            mapped = False
            d.sync()

    def parse_state(blob: dict) -> HudState:
        steps = [StepView(title=s.get("title", ""), expect=s.get("expect", ""),
                          status=s.get("status", "pending"))
                 for s in blob.get("steps") or []]
        tgt = blob.get("target")
        cand = blob.get("candidate")
        return HudState(
            mode=blob.get("mode", "replay"),
            tokens=int(blob.get("tokens") or 0),
            flow_name=blob.get("flow_name") or "Untitled flow",
            steps=steps,
            current=int(blob.get("current") or 0),
            target=tuple(tgt) if tgt else None,
            candidate=tuple(cand) if cand else None,
            candidate_label=blob.get("candidate_label") or "",
            match=bool(blob.get("match", True)),
            tag=blob.get("tag") or "",
            screen=(sw, sh),
        )

    # Bind socket
    try:
        if os.path.exists(sock_path):
            os.unlink(sock_path)
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o600)
    srv.listen(4)
    srv.setblocking(False)
    print(f"afterimage-overlay listening on {sock_path} display={os.environ['DISPLAY']} {sw}x{sh}",
          flush=True)

    clients: dict[int, tuple[socket.socket, bytearray]] = {}
    running = True
    while running:
        dead=[]
        for fn,(c,_) in list(clients.items()):
            try:
                if c.fileno() < 0:
                    dead.append(fn)
            except Exception:
                dead.append(fn)
        for fn in dead:
            try: clients.pop(fn)[0].close()
            except Exception: pass
        rlist = [srv, d] + [c[0] for c in clients.values()]
        try:
            ready, _, _ = select.select(rlist, [], [], 0.25)
        except (InterruptedError, ValueError):
            continue
        # keep above the desktop + drain X events (repaint on Expose)
        try:
            if mapped:
                win.configure(stack_mode=X.Above)
            while d.pending_events():
                ev = d.next_event()
                if ev.type == X.Expose and getattr(ev, "count", 0) == 0 and last is not None:
                    _put_image(win, gc, last, X, apply_shape=False)
            d.flush()
        except Exception:
            pass
        for fd in ready:
            if fd is d:
                continue
            if fd is srv:
                conn, _ = srv.accept()
                conn.setblocking(False)
                clients[conn.fileno()] = (conn, bytearray())
                continue
            try:
                fn = fd.fileno()
            except Exception:
                continue
            if fn not in clients:
                continue
            conn, buf = clients[fn]
            try:
                chunk = conn.recv(65536)
            except BlockingIOError:
                continue
            if not chunk:
                try:
                    conn.close()
                except Exception:
                    pass
                clients.pop(fn, None)
                continue
            buf.extend(chunk)
            while b"\n" in buf:
                line, _, rest = buf.partition(b"\n")
                buf[:] = rest
                try:
                    msg = json.loads(line.decode() or "{}")
                except Exception as e:
                    try:
                        conn.sendall(json.dumps({"ok": False, "error": str(e)}).encode() + b"\n")
                    except Exception:
                        pass
                    continue
                op = msg.get("op")
                reply: dict = {"ok": True, "op": op}
                try:
                    if op == "show":
                        st = parse_state(msg.get("state") or msg)
                        # Optional background (RGB PNG path) for glass blur
                        bg = None
                        bgp = msg.get("background")
                        if bgp and Path(bgp).is_file():
                            bg = Image.open(bgp).convert("RGB")
                        paint(render(st, background=bg))
                    elif op == "hide":
                        hide()
                    elif op == "ping":
                        reply["display"] = os.environ.get("DISPLAY")
                        reply["size"] = [sw, sh]
                    elif op in ("quit", "exit"):
                        running = False
                    else:
                        reply = {"ok": False, "error": f"unknown op {op}"}
                except Exception as e:
                    reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                try:
                    conn.sendall(json.dumps(reply).encode() + b"\n")
                except Exception:
                    pass
    hide()
    for c, _ in list(clients.values()):
        try: c.close()
        except Exception: pass
    srv.close()
    try: os.unlink(sock_path)
    except Exception: pass
    win.destroy(); d.sync()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOCK,
        sys.argv[2] if len(sys.argv) > 2 else None)
