"""Locate a UI control in a screenshot via ctx.llm (host-owned credentials)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


LOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "number", "description": "Normalized 0-1000 x of the target center (0=left)."},
        "y": {"type": "number", "description": "Normalized 0-1000 y of the target center (0=top)."},
        "label": {"type": "string"},
        "found": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["x", "y", "found"],
}


def locate(ctx, image_path: str, target: str, size: tuple[int, int],
           model: Optional[str] = "qwen3-vl-plus") -> dict[str, Any]:
    """Return pixel coordinates in the given image. Uses ctx.llm so the plugin
    never reads provider keys. Falls back to the session model if model override
    is not granted."""
    from agent.plugin_llm import PluginLlmImageInput, PluginLlmTextInput, PluginLlmTrustError

    data = Path(image_path).read_bytes()
    w, h = size
    instructions = (
        "You ground UI elements for a computer-use agent. "
        "Look at the screenshot and find the described target. "
        "Return JSON with x,y in a 0-1000 normalized space of this image "
        "(0,0 is the top-left, 1000,1000 is the bottom-right), the visible label, "
        "found (boolean), and confidence 0-1."
    )
    inputs = [
        PluginLlmImageInput(data=data, mime_type="image/png"),
        PluginLlmTextInput(text=f"Target: {target}"),
    ]
    result = None
    used_model = model
    try:
        result = ctx.llm.complete_structured(
            instructions=instructions, input=inputs, json_schema=LOCATE_SCHEMA,
            json_mode=True, schema_name="afterimage_locate",
            model=model, max_tokens=120, timeout=60,
            purpose="afterimage_locate",
        )
    except PluginLlmTrustError:
        used_model = None
        result = ctx.llm.complete_structured(
            instructions=instructions, input=inputs, json_schema=LOCATE_SCHEMA,
            json_mode=True, schema_name="afterimage_locate",
            max_tokens=120, timeout=60, purpose="afterimage_locate",
        )
    parsed = result.parsed if result else None
    text = (result.text if result else "") or ""
    if not isinstance(parsed, dict):
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)[:2]]
        parsed = {"x": nums[0], "y": nums[1], "found": len(nums) >= 2} if len(nums) >= 2 else {"found": False}
    if not parsed.get("found", True):
        return {"error": "target not found", "raw": text[:300], "model": result.model if result else used_model}
    x = float(parsed["x"])
    y = float(parsed["y"])
    # Accept either 0-1000 or already-pixel values (if x or y > 1000, treat as pixels).
    if 0 <= x <= 1000 and 0 <= y <= 1000:
        px, py = round(x * w / 1000), round(y * h / 1000)
        space = "normalized-1000"
    else:
        px, py = round(x), round(y)
        space = "pixels"
    usage = result.usage if result else None
    tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return {
        "coordinate": [px, py],
        "label": parsed.get("label") or target,
        "confidence": parsed.get("confidence"),
        "size": [w, h],
        "screenshot": image_path,
        "model": result.model if result else used_model,
        "tokens": tokens,
        "space": space,
    }
