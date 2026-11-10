"""Afterimage — record a computer-use flow once, rehearse it with a visible HUD,
and replay it at zero tokens. Only a drifted step is handed back to the AI."""
from __future__ import annotations

import json
import logging

from . import schemas, tools
from . import runtime as rt

logger = logging.getLogger(__name__)

HINT = (
    "[afterimage] For desktop clicks, call afterimage_locate(target=...) on the latest "
    "computer_use capture and pass its pixel `coordinate` unchanged. Use "
    "delivery_mode='foreground' on Linux/X11 if background delivery has no effect. "
    "To save a flow: afterimage_begin_record(...) before the first click, then "
    "afterimage_end_record. Rehearse or replay with afterimage_rehearse / afterimage_replay."
)


def _hint(**kw):
    return {"context": HINT}


def _on_session_finalize(**kw):
    try:
        rt.hide_hud()
    except Exception:
        pass


def _slash(ctx, raw: str) -> str:
    parts = (raw or "").strip().split()
    cmd = (parts[0] if parts else "help").lower()
    rest = parts[1:]
    if cmd in ("help", ""):
        return (
            "Afterimage commands:\n"
            "  /afterimage record <name>   start recording computer_use actions\n"
            "  /afterimage stop            save the flow\n"
            "  /afterimage list            saved flows\n"
            "  /afterimage rehearse <name> visible rehearsal, repair drifted steps\n"
            "  /afterimage replay <name>   zero-token replay (stops on drift unless you add --repair)\n"
        )
    if cmd == "record":
        name = rest[0] if rest else "untitled"
        return tools.begin_record({"name": name})
    if cmd in ("stop", "end"):
        return tools.end_record({})
    if cmd == "list":
        return tools.list_flows({})
    if cmd == "rehearse" and rest:
        return tools.rehearse({"name": rest[0], "repair": True})
    if cmd == "replay" and rest:
        repair = "--repair" in rest
        return tools.replay({"name": rest[0], "repair": repair})
    return "Usage: /afterimage help"


def _cli(args):
    sub = getattr(args, "afterimage_cmd", None)
    if sub == "list":
        print(tools.list_flows({}))
    elif sub == "rehearse":
        print(tools.rehearse({"name": args.name, "repair": not getattr(args, "no_repair", False)}))
    elif sub == "replay":
        print(tools.replay({"name": args.name, "repair": getattr(args, "repair", False)}))
    elif sub == "hud-check":
        from .overlay_draw import HudState, StepView, render
        st = HudState(mode="replay", tokens=0, flow_name="hud-check",
                      steps=[StepView("Click “Export”", "Save dialog opens", "current"),
                             StepView("Click “Save”", "→ “Saved”", "pending")],
                      target=(100, 100, 180, 140), match=True)
        out = "/tmp/afterimage-hud-check.png"
        render(st).save(out)
        print(out)
    else:
        print("Usage: hermes afterimage <list|rehearse|replay|hud-check>")


def _setup_cli(subparser):
    subs = subparser.add_subparsers(dest="afterimage_cmd")
    subs.add_parser("list", help="List saved flows")
    p = subs.add_parser("rehearse", help="Rehearse a flow with the HUD")
    p.add_argument("name")
    p.add_argument("--no-repair", action="store_true")
    p = subs.add_parser("replay", help="Zero-token replay of a flow")
    p.add_argument("name")
    p.add_argument("--repair", action="store_true")
    subs.add_parser("hud-check", help="Render a sample Direction B HUD to /tmp")
    subparser.set_defaults(func=_cli)


def register(ctx):
    rt.set_ctx(ctx)
    ctx.register_tool(name="afterimage_locate", toolset="afterimage",
                      schema=schemas.LOCATE, handler=tools.locate,
                      description="Qwen-VL grounding for computer_use", emoji="🎯")
    ctx.register_tool(name="afterimage_begin_record", toolset="afterimage",
                      schema=schemas.BEGIN_RECORD, handler=tools.begin_record,
                      description="Start recording a computer-use flow", emoji="⏺")
    ctx.register_tool(name="afterimage_end_record", toolset="afterimage",
                      schema=schemas.END_RECORD, handler=tools.end_record,
                      description="Save the recorded flow", emoji="⏹")
    ctx.register_tool(name="afterimage_list", toolset="afterimage",
                      schema=schemas.LIST_FLOWS, handler=tools.list_flows,
                      description="List saved Afterimage flows", emoji="📋")
    ctx.register_tool(name="afterimage_rehearse", toolset="afterimage",
                      schema=schemas.REHEARSE, handler=tools.rehearse,
                      description="Rehearse a flow with the Afterimage HUD", emoji="▶")
    ctx.register_tool(name="afterimage_replay", toolset="afterimage",
                      schema=schemas.REPLAY, handler=tools.replay,
                      description="Zero-token replay of a saved flow", emoji="⏩")
    ctx.register_hook("post_tool_call", tools.on_post_tool_call)
    ctx.register_hook("pre_llm_call", _hint)
    ctx.register_hook("post_api_request", tools.on_api_tokens)
    ctx.register_hook("post_auxiliary_call", tools.on_api_tokens)
    ctx.register_hook("on_session_finalize", _on_session_finalize)
    ctx.register_command("afterimage", lambda raw: _slash(ctx, raw),
                         description="Record, rehearse, or replay an Afterimage flow")
    ctx.register_cli_command(name="afterimage", help="Record / rehearse / replay desktop flows",
                             setup_fn=_setup_cli, handler_fn=_cli)
