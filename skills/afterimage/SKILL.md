---
name: afterimage
description: Record a Hermes computer-use flow, rehearse it with the Afterimage HUD, and replay matches at zero tokens.
---

# Afterimage

When the user wants to record, rehearse, or replay a desktop flow:

1. Enable the `computer_use` and `afterimage` toolsets.
2. Call `afterimage_begin_record` with a short name and planned step titles (`title`, `expect`).
3. For each click: `computer_use` capture, then `afterimage_locate`, then `computer_use` click with that pixel coordinate, `delivery_mode=foreground` on Linux/X11, and the target `pid` and `window_id` (or a `window_title` such as `ChatGPT` so the plugin can re-attach). Chrome `--app` windows are not listed as a unique app name.
4. `afterimage_end_record`.
5. `afterimage_rehearse` to preview (green = match / 0 tokens; red = drift, only that step is repaired).
6. `afterimage_replay` for a full-speed zero-token run. Pass `times=N` to repeat a fixed-position sequence (for example after a list slides up).

Do not guess raw pixel coordinates. Do not read API keys. Do not skip Hermes approvals.
Do not open or log into real chatgpt.com; the official demo uses the local sidebar mock only.
