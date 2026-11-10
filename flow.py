"""Persisted Afterimage flows under the plugin data directory."""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

FLOW_VERSION = 1


def _safe(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip())[:80].strip("-")
    return s or "untitled"


def data_root() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir
        return plugin_data_dir("afterimage")
    except Exception:
        fallback = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "plugin-data" / "afterimage"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def flows_root() -> Path:
    p = data_root() / "flows"
    p.mkdir(parents=True, exist_ok=True)
    return p


def flow_dir(name: str) -> Path:
    p = flows_root() / _safe(name)
    p.mkdir(parents=True, exist_ok=True)
    (p / "steps").mkdir(exist_ok=True)
    return p


def flow_path(name: str) -> Path:
    return flow_dir(name) / "flow.json"


def load_flow(name: str) -> dict[str, Any]:
    p = flow_path(name)
    if not p.exists():
        raise FileNotFoundError(f"No Afterimage flow named {name!r}")
    return json.loads(p.read_text(encoding="utf-8"))


def save_flow(flow: dict[str, Any]) -> Path:
    flow = dict(flow)
    flow.setdefault("version", FLOW_VERSION)
    flow["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = flow_path(flow["name"])
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(flow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def list_flows() -> list[dict[str, Any]]:
    out = []
    for d in sorted(flows_root().iterdir()):
        fp = d / "flow.json"
        if fp.is_file():
            try:
                f = json.loads(fp.read_text(encoding="utf-8"))
                out.append({"name": f.get("name", d.name), "steps": len(f.get("steps") or []),
                            "updated": f.get("updated", ""), "description": f.get("description", "")})
            except Exception:
                continue
    return out


def copy_image(src: str | Path, dest: Path) -> Optional[str]:
    src = Path(src)
    if not src.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return str(dest)
