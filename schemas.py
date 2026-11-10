"""Tool schemas shown to the model."""

LOCATE = {
    "name": "afterimage_locate",
    "description": (
        "Find a UI element in the most recent computer_use screenshot and return its "
        "PIXEL coordinate [x, y] (relative to that capture), ready to pass as "
        "`coordinate` to computer_use click. Use this instead of guessing pixels."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "What to find, e.g. the button labeled Export."},
        },
        "required": ["target"],
    },
}

BEGIN_RECORD = {
    "name": "afterimage_begin_record",
    "description": (
        "Start recording a desktop flow from subsequent computer_use actions "
        "(clicks, typing, keys). Call this BEFORE the first click. Optional planned_steps "
        "give each recorded click a title and expected outcome for the rehearsal HUD."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short flow name, e.g. monthly-export."},
            "description": {"type": "string"},
            "planned_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": 'e.g. Click “Export”'},
                        "expect": {"type": "string", "description": "e.g. Save dialog opens"},
                    },
                    "required": ["title"],
                },
            },
        },
        "required": ["name"],
    },
}

END_RECORD = {
    "name": "afterimage_end_record",
    "description": "Stop recording and save the flow (screenshots + actions) so it can be rehearsed or replayed at zero tokens.",
    "parameters": {"type": "object", "properties": {}},
}

LIST_FLOWS = {
    "name": "afterimage_list",
    "description": "List saved Afterimage flows.",
    "parameters": {"type": "object", "properties": {}},
}

REHEARSE = {
    "name": "afterimage_rehearse",
    "description": (
        "Rehearse a saved flow with the on-screen Afterimage HUD. Before each step, "
        "compare the live screenshot to the recorded one. Matching steps play in green "
        "at 0 tokens. A mismatched step turns red, the token meter turns purple, and "
        "ONLY that step is handed to the AI to repair (then written back). "
        "Requires the computer_use toolset to be enabled."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "repair": {"type": "boolean", "description": "If true (default), a drifted step is repaired and saved."},
        },
        "required": ["name"],
    },
}

REPLAY = {
    "name": "afterimage_replay",
    "description": (
        "Full-speed zero-token replay of a saved flow, with the live token counter "
        "held at 0 (green). If a step has drifted and repair=true, that step is handed "
        "to the AI (purple, counter rises) and written back."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "repair": {"type": "boolean", "description": "Default false: stop on drift rather than calling the AI."},
            "times": {"type": "integer", "description": "Run the same fixed-position sequence this many times (e.g. delete the next N chats after the list slides up). Default 1, max 20."},
        },
        "required": ["name"],
    },
}
