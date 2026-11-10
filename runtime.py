"""Process-wide Afterimage state: recording buffer, token totals, overlay sidecar client."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

PLUGIN_DIR = Path(__file__).resolve().parent
SOCK = os.environ.get("AFTERIMAGE_SOCK", "/tmp/afterimage-overlay.sock")
DISPLAY = os.environ.get("DISPLAY", ":0")

_lock = threading.Lock()
recording: bool = False
record_name: str = ""
record_description: str = ""
planned_steps: list[dict] = []
recorded_steps: list[dict] = []
last_capture: dict[str, Any] = {}  # path, width, height, pid, window_id, title, app
token_total: int = 0
hud_mode: str = "replay"  # replay | repair
overlay_proc: Optional[subprocess.Popen] = None
_ctx = None  # PluginContext, set in register()


def set_ctx(ctx) -> None:
    global _ctx
    _ctx = ctx


def ctx():
    return _ctx


def reset_tokens() -> None:
    global token_total
    with _lock:
        token_total = 0


def add_tokens(n: int) -> None:
    global token_total
    if not n:
        return
    with _lock:
        token_total += int(n)


def _which_python() -> str:
    """Prefer an interpreter that already has Pillow + python-xlib (sidecar venv)."""
    candidates = [
        os.environ.get("AFTERIMAGE_PYTHON", ""),
        sys.executable,
    ]
    for p in candidates:
        if not p or not Path(p).exists():
            continue
        r = subprocess.run([p, "-c", "import PIL, Xlib, mss"], capture_output=True)
        if r.returncode == 0:
            return p
    return sys.executable


def ensure_overlay() -> None:
    global overlay_proc
    if _ping():
        return
    py = _which_python()
    log = Path("/tmp/afterimage-overlay.log")
    overlay_proc = subprocess.Popen(
        [py, str(PLUGIN_DIR / "overlay_server.py"), SOCK, DISPLAY],
        stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True,
        env={**os.environ, "DISPLAY": DISPLAY, "AFTERIMAGE_SOCK": SOCK},
    )
    for _ in range(40):
        if _ping():
            return
        time.sleep(0.1)
    raise RuntimeError(f"Afterimage overlay failed to start (see {log})")


def _ping() -> bool:
    try:
        r = rpc({"op": "ping"}, start=False, timeout=0.3)
        return bool(r.get("ok"))
    except Exception:
        return False


def rpc(msg: dict, start: bool = True, timeout: float = 5.0) -> dict:
    if start and msg.get("op") not in ("quit", "ping"):
        ensure_overlay()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(SOCK)
    sock.sendall((json.dumps(msg) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.close()
    if not buf:
        return {"ok": False, "error": "empty overlay reply"}
    return json.loads(buf.split(b"\n", 1)[0].decode())


def show_hud(state: dict) -> dict:
    return rpc({"op": "show", "state": state})


def hide_hud() -> None:
    try:
        rpc({"op": "hide"}, start=False, timeout=1)
    except Exception:
        pass


def stop_overlay() -> None:
    global overlay_proc
    try:
        rpc({"op": "quit"}, start=False, timeout=1)
    except Exception:
        pass
    if overlay_proc and overlay_proc.poll() is None:
        try:
            overlay_proc.terminate()
        except Exception:
            pass
    overlay_proc = None


def window_geometry(title: Optional[str] = None, window_id: Optional[int] = None) -> Optional[dict]:
    """Locate a mapped X window. Returns screen-absolute x,y,w,h and window_id."""
    import subprocess as sp
    ids: list[str] = []
    if window_id:
        ids = [str(window_id)]
    elif title:
        import re as _re
        r = sp.run(["xdotool", "search", "--name", "^" + _re.escape(title) + "$"], capture_output=True, text=True)
        ids = r.stdout.split()
        if not ids:
            r = sp.run(["xdotool", "search", "--name", title], capture_output=True, text=True)
            ids = r.stdout.split()
    for wid in ids:
        info = sp.run(["xwininfo", "-id", wid], capture_output=True, text=True).stdout
        if "IsViewable" not in info and "is mapped" not in info.lower():
            # still accept if Absolute is present and Map State: IsViewable
            if "IsViewable" not in info:
                continue
        geo = {}
        for line in info.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            try:
                geo[k.strip()] = int(v.strip())
            except ValueError:
                continue
        x = geo.get("Absolute upper-left X")
        y = geo.get("Absolute upper-left Y")
        w = geo.get("Width")
        h = geo.get("Height")
        if None not in (x, y, w, h):
            return {"window_id": int(wid, 0) if str(wid).startswith("0x") else int(wid),
                    "x": x, "y": y, "w": w, "h": h}
    return None


def window_title(window_id: Optional[int]) -> str:
    """Live title of an X window ("" if unknown), stored with a recording so a
    relaunched window (new pid / window id) can be found again."""
    if not window_id:
        return ""
    try:
        r = subprocess.run(["xdotool", "getwindowname", str(window_id)],
                           capture_output=True, text=True, timeout=2)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def capture_to_screen_box(coord, capture_size, window_geo) -> tuple[int, int, int, int]:
    """Map a click (cx,cy) in a capture of size (cw,ch) onto a screen-absolute target box."""
    cx, cy = coord
    cw, ch = capture_size
    x, y, w, h = window_geo["x"], window_geo["y"], window_geo["w"], window_geo["h"]
    # If the capture is the client area and xwininfo includes a title bar, shift down.
    off_x = 0
    off_y = 0
    if w and h and cw and ch and (abs(w - cw) > 4 or abs(h - ch) > 4):
        off_x = max(0, (w - cw) // 2)
        off_y = max(0, h - ch)  # typical WM decoration is on top
    half_w, half_h = 36, 22
    sx = x + off_x + int(cx)
    sy = y + off_y + int(cy)
    return (sx - half_w, sy - half_h, sx + half_w, sy + half_h)


def resolve_pid(window_id: Optional[int] = None, title: Optional[str] = None) -> Optional[int]:
    """Read _NET_WM_PID for a mapped window (Chrome --app windows have a pid but no unique app name)."""
    geo = window_geometry(title=title, window_id=window_id)
    if not geo:
        return None
    wid = geo["window_id"]
    try:
        r = subprocess.run(["xprop", "-id", str(wid), "_NET_WM_PID"],
                           capture_output=True, text=True, timeout=2)
        import re
        m = re.search(r"=\s*(\d+)", r.stdout or "")
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None
