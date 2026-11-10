"""Tool handlers. Always return a JSON string. Never raise. Never read API keys."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from . import compare as compare_mod
from . import flow as flow_mod
from . import grounding
from . import runtime as rt

RECORDABLE = {"click", "double_click", "right_click", "middle_click", "type", "key", "drag", "scroll"}


def _ok(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


def _err(msg: str, **kw) -> str:
    return json.dumps({"error": msg, **kw}, ensure_ascii=False)


def locate(args: dict, **kw) -> str:
    try:
        target = (args or {}).get("target", "").strip()
        cap = rt.last_capture
        if not target:
            return _err("need target")
        if not cap.get("path") or not Path(cap["path"]).is_file():
            return _err("call computer_use capture first (no recent screenshot)")
        ctx = rt.ctx()
        if ctx is None:
            return _err("plugin context is not ready")
        out = grounding.locate(ctx, cap["path"], target, (cap["width"], cap["height"]))
        if "tokens" in out:
            rt.add_tokens(out["tokens"])
        return _ok(**out)
    except Exception as e:
        return _err(f"locate failed: {type(e).__name__}: {e}")


def begin_record(args: dict, **kw) -> str:
    name = (args or {}).get("name") or "untitled"
    with rt._lock:
        rt.recording = True
        rt.record_name = name
        rt.record_description = (args or {}).get("description") or ""
        rt.planned_steps = list((args or {}).get("planned_steps") or [])
        rt.recorded_steps = []
    return _ok(ok=True, recording=name, planned_steps=len(rt.planned_steps),
               hint="Now drive the desktop with computer_use. Call afterimage_end_record when finished.")


def end_record(args: dict, **kw) -> str:
    with rt._lock:
        if not rt.recording and not rt.recorded_steps:
            return _err("not recording and no steps buffered")
        name = rt.record_name or "untitled"
        steps = list(rt.recorded_steps)
        desc = rt.record_description
        planned = list(rt.planned_steps)
        rt.recording = False
    if not steps:
        return _err("no computer_use actions were recorded")
    dest = flow_mod.flow_dir(name)
    saved = []
    for i, step in enumerate(steps, 1):
        s = dict(step)
        if s.get("expected_src"):
            p = flow_mod.copy_image(s["expected_src"], dest / "steps" / f"{i:03d}.png")
            if p:
                s["expected_image"] = f"steps/{i:03d}.png"
        s.pop("expected_src", None)
        if i <= len(planned):
            s.setdefault("title", planned[i - 1].get("title"))
            s.setdefault("expect", planned[i - 1].get("expect"))
        s.setdefault("title", f"Step {i}: {s.get('action', 'action')}")
        s.setdefault("expect", "")
        saved.append(s)
    flow = {"name": name, "description": desc, "steps": saved, "version": 1}
    path = flow_mod.save_flow(flow)
    return _ok(ok=True, name=name, steps=len(saved), path=str(path),
               titles=[s.get("title") for s in saved])


def list_flows(args: dict, **kw) -> str:
    return _ok(flows=flow_mod.list_flows())


def _remember_capture(args: dict, result: Any) -> None:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    path = width = height = None
    title = ""
    try:
        d = json.loads(text)
    except Exception:
        d = {}
    if isinstance(d, dict):
        path = d.get("screenshot_path") or d.get("path")
        width = d.get("width")
        height = d.get("height")
        title = d.get("window_title") or ""
        if not width and isinstance(d.get("summary"), str):
            import re
            m = re.search(r"capture mode=\w+ (\d+)x(\d+)", d["summary"])
            if m:
                width, height = int(m.group(1)), int(m.group(2))
            m = re.search(r"(/[^\s\"')]+computer_use_[0-9a-f]+\.png)", d["summary"])
            if m and not path:
                path = m.group(1)
    if not path:
        import re
        m = re.search(r"(/[^\s\"')]+computer_use_[0-9a-f]+\.png)", text)
        if m:
            path = m.group(1)
        m = re.search(r"capture mode=\w+ (\d+)x(\d+)", text)
        if m:
            width, height = int(m.group(1)), int(m.group(2))
    if path:
        # Snapshot the capture now: the driver may reuse or overwrite the same
        # screenshot path on the next capture, which would make every recorded
        # step point at the final frame.
        try:
            import shutil, tempfile, uuid
            snap_dir = Path(tempfile.gettempdir()) / "afterimage-captures"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap = snap_dir / f"{uuid.uuid4().hex}.png"
            shutil.copyfile(path, snap)
            path = str(snap)
        except Exception:
            pass
        rt.last_capture = {
            "path": path, "width": int(width or 0), "height": int(height or 0),
            "pid": (args or {}).get("pid"), "window_id": (args or {}).get("window_id"),
            "app": (args or {}).get("app") or "", "title": title,
        }


def on_post_tool_call(tool_name=None, args=None, result=None, **kw) -> None:
    if tool_name != "computer_use":
        return
    args = args or {}
    action = args.get("action")
    if action == "capture":
        _remember_capture(args, result)
        return
    if not rt.recording or action not in RECORDABLE:
        return
    cap = dict(rt.last_capture)
    step = {
        "action": action,
        "coordinate": args.get("coordinate"),
        "pid": args.get("pid") or cap.get("pid"),
        "window_id": args.get("window_id") or cap.get("window_id"),
        "app": args.get("app") or cap.get("app") or "",
        "window_title": cap.get("title") or rt.window_title(args.get("window_id") or cap.get("window_id")) or "",
        "delivery_mode": args.get("delivery_mode") or "foreground",
        "text": args.get("text"),
        "keys": args.get("keys"),
        "capture_width": cap.get("width"),
        "capture_height": cap.get("height"),
        "expected_src": cap.get("path"),
        "element": args.get("element"),
    }
    with rt._lock:
        rt.recorded_steps.append(step)


def on_api_tokens(usage=None, **kw) -> None:
    if not usage:
        return
    if isinstance(usage, dict):
        n = usage.get("total_tokens") or (
            (usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            + (usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        )
        # Only count during repair/record assist, not during zero-token replay itself.
        if rt.hud_mode == "repair":
            rt.add_tokens(int(n or 0))


def _with_pid(action: dict) -> dict:
    """Chrome --app is not in cua list_apps by product name. Re-resolve pid and
    window_id from the live window title so a relaunch still clicks the same app."""
    out = dict(action)
    title = out.get("window_title")
    # A recorded window id that still exists wins; otherwise re-find the window by title.
    # X reuses window ids, so always refresh the pid from _NET_WM_PID.
    if out.get("window_id") and rt.window_geometry(window_id=out["window_id"]):
        live_title = rt.window_title(out["window_id"])
        if not title or live_title == title:
            pid = rt.resolve_pid(window_id=out["window_id"])
            if pid:
                out["pid"] = pid
            return out
    geo = rt.window_geometry(title=title) if title else None
    if geo:
        out["window_id"] = geo["window_id"]
        pid = rt.resolve_pid(window_id=geo["window_id"], title=title)
        if pid:
            out["pid"] = pid
        return out
    if not out.get("pid"):
        pid = rt.resolve_pid(window_id=out.get("window_id"), title=title)
        if pid:
            out["pid"] = pid
    return out


def _dispatch(ctx, action: dict) -> str:
    action = _with_pid(action)
    payload = {k: v for k, v in action.items() if v is not None and k in {
        "action", "coordinate", "pid", "window_id", "app", "delivery_mode",
        "text", "keys", "element", "mode", "capture_after",
    }}
    return ctx.dispatch_tool("computer_use", payload)


def _capture_step(ctx, step: dict) -> Optional[str]:
    args = {"action": "capture", "mode": "vision"}
    if step.get("pid"):
        args["pid"] = step["pid"]
    if step.get("window_id"):
        args["window_id"] = step["window_id"]
    if step.get("app"):
        args["app"] = step["app"]
    if step.get("window_title"):
        args["window_title"] = step["window_title"]
    args = _with_pid(args)
    rt.last_capture = {}  # never compare against a stale frame from an earlier capture
    raw = ctx.dispatch_tool("computer_use", args)
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    if text.lstrip().startswith('{"error"'):
        return None
    _remember_capture(args, raw)
    return rt.last_capture.get("path")


def _target_box(step: dict, coord: list) -> Optional[list]:
    geo = None
    if step.get("window_title"):
        geo = rt.window_geometry(title=step["window_title"])
    if not geo and step.get("window_id"):
        geo = rt.window_geometry(window_id=step["window_id"])
    if not geo or not coord:
        return None
    size = (step.get("capture_width") or 0, step.get("capture_height") or 0)
    box = rt.capture_to_screen_box(coord, size, geo)
    return list(box)


def _hud(flow, steps_view, current, match, tokens, mode, target, candidate=None, cand_label="", tag="", expect=None):
    rt.hud_mode = mode
    state = {
        "mode": mode,
        "tokens": tokens if mode == "repair" else 0 if mode == "replay" else tokens,
        "flow_name": flow.get("description") or flow.get("name") or "flow",
        "steps": steps_view,
        "current": current,
        "target": target,
        "candidate": candidate,
        "candidate_label": cand_label,
        "match": match,
        "tag": tag,
    }
    # During repair the counter should show the running total; during replay, 0.
    if mode == "replay":
        state["tokens"] = 0
    else:
        state["tokens"] = rt.token_total
    try:
        rt.show_hud(state)
    except Exception:
        pass


def _play(args: dict, *, default_repair: bool, mode_label: str, **kw) -> str:
    try:
        name = (args or {}).get("name")
        repair = (args or {}).get("repair")
        if repair is None:
            repair = default_repair
        flow = flow_mod.load_flow(name)
        steps = flow.get("steps") or []
        if not steps:
            return _err("flow has no steps")
        ctx = rt.ctx()
        if ctx is None:
            return _err("plugin context is not ready")
        dest = flow_mod.flow_dir(name)
        rt.reset_tokens()
        rt.hud_mode = "replay"
        log = []
        repaired = False
        views = [{"title": s.get("title") or f"Step {i+1}",
                  "expect": s.get("expect") or "",
                  "status": "pending"} for i, s in enumerate(steps)]
        for i, step in enumerate(steps):
            views[i]["status"] = "current"
            title = step.get("title") or f"Step {i+1}"
            expect = step.get("expect") or ""
            coord = step.get("coordinate")
            img = dest / step["expected_image"] if step.get("expected_image") else None
            path = _capture_step(ctx, step)
            if not path:
                log.append({"step": i + 1, "error": "capture failed (window gone or not found by title)"})
                return _ok(ok=False, log=log, error="capture failed: target window not found")
            if not img or not img.is_file() or not coord:
                log.append({"step": i + 1, "error": "missing capture or coordinate"})
                return _ok(ok=False, log=log, error="missing capture or coordinate")
            result = compare_mod.compare(img, path, tuple(coord))
            target = _target_box(step, list(result.coordinate if result.match else coord))
            tag = f'{i+1:02d}  CLICK  "{title.replace("Click ", "").replace("“", "").replace("”", "").strip()}"'
            if result.match:
                views[i]["expect"] = expect or "looks the same"
                _hud(flow, views, i, True, 0, "replay", target, tag=f'{i+1:02d}  CLICK  "{_short(title)}"')
                time.sleep(0.7 if mode_label == "rehearse" else 0.25)
                click = dict(step)
                click["coordinate"] = list(result.coordinate)
                click["delivery_mode"] = click.get("delivery_mode") or "foreground"
                _dispatch(ctx, click)
                time.sleep(0.4)
                log.append({"step": i + 1, "status": "ok", "diff": result.diff,
                            "coordinate": list(result.coordinate), "tokens": 0})
                views[i]["status"] = "done"
                continue

            # Drift
            views[i]["status"] = "bad"
            views[i]["expect"] = f"pixels differ · Δ {result.diff}"
            _hud(flow, views, i, False, rt.token_total, "repair" if repair else "repair",
                 target, tag=f"{i+1:02d}  TARGET MISSING")
            time.sleep(0.8)
            if not repair:
                log.append({"step": i + 1, "status": "mismatch", "diff": result.diff})
                return _ok(ok=False, reason="mismatch", log=log, stopped_at=i + 1,
                           hint="Re-run with repair=true to hand only this step to the AI.")
            rt.hud_mode = "repair"
            loc = grounding.locate(
                ctx, path, f'The control that used to be: {title}. {expect}'.strip(),
                (rt.last_capture.get("width") or step.get("capture_width") or 0,
                 rt.last_capture.get("height") or step.get("capture_height") or 0),
            )
            rt.add_tokens(int(loc.get("tokens") or 0))
            if loc.get("error"):
                log.append({"step": i + 1, "status": "repair-failed", "error": loc})
                _hud(flow, views, i, False, rt.token_total, "repair", target, tag=f"{i+1:02d}  TARGET MISSING")
                return _ok(ok=False, reason="repair-failed", log=log, locate=loc)
            new_coord = loc["coordinate"]
            cand = _target_box(step, new_coord)
            _hud(flow, views, i, False, rt.token_total, "repair", target, candidate=cand,
                 cand_label=f'AI  candidate  "{loc.get("label") or _short(title)}"  {loc.get("confidence") or ""}'.strip(),
                 tag=f"{i+1:02d}  TARGET MISSING")
            time.sleep(0.8)
            click = dict(step)
            click["coordinate"] = list(new_coord)
            click["delivery_mode"] = click.get("delivery_mode") or "foreground"
            _dispatch(ctx, click)
            time.sleep(0.5)
            # Write the repair back: new coords + fresh expected screenshot
            step["coordinate"] = list(new_coord)
            step["repaired_from"] = list(coord)
            step["repair_diff"] = result.diff
            if path and Path(path).is_file():
                p = flow_mod.copy_image(path, dest / "steps" / f"{i+1:03d}.png")
                if p:
                    step["expected_image"] = f"steps/{i+1:03d}.png"
            flow["steps"] = steps
            flow_mod.save_flow(flow)
            repaired = True
            log.append({"step": i + 1, "status": "repaired", "diff": result.diff,
                        "old": coord, "new": new_coord, "tokens": loc.get("tokens") or 0,
                        "label": loc.get("label")})
            views[i]["status"] = "done"
            views[i]["expect"] = expect
        # Success HUD
        last = steps[-1]
        _hud(flow, views, max(0, len(steps) - 1), True, 0, "replay",
             _target_box(last, last.get("coordinate") or [0, 0]), tag="DONE")
        time.sleep(0.6)
        if mode_label == "replay" or True:
            # keep HUD up briefly so a screenshot can catch the green 0-token state
            pass
        return _ok(ok=True, name=name, steps=len(steps), repaired=repaired,
                   tokens=rt.token_total, log=log)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"{mode_label} failed: {type(e).__name__}: {e}")


def _short(title: str) -> str:
    t = title.replace("Click ", "").replace("“", "").replace("”", "").replace('"', "").strip()
    t = t or title
    return t if len(t) <= 28 else t[:27].rstrip() + "…"


def rehearse(args: dict, **kw) -> str:
    return _play(args, default_repair=True, mode_label="rehearse", **kw)


def replay(args: dict, **kw) -> str:
    times = int((args or {}).get("times") or 1)
    times = max(1, min(times, 20))
    if times == 1:
        return _play(args, default_repair=False, mode_label="replay", **kw)
    runs = []
    tokens = 0
    repaired = False
    ok = True
    for i in range(times):
        r = json.loads(_play(args, default_repair=False, mode_label="replay", **kw))
        runs.append({"pass": i + 1, **r})
        tokens += int(r.get("tokens") or 0)
        repaired = repaired or bool(r.get("repaired"))
        if not r.get("ok"):
            ok = False
            break
    return _ok(ok=ok, name=(args or {}).get("name"), times=times, tokens=tokens,
               repaired=repaired, log=runs)
