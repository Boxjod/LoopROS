"""Portable text branding: no image protocol, cursor tricks or terminal claims."""
import os
from pathlib import Path
import shutil

from .._version import __version__ as VERSION
TAGLINE = "Build robots. Close the loop."

# Monochrome infinity with mirrored eye openings and four antennae.
LOGO = (
    "         █",
    "     ▟▀▀▀▀▀▀▀▙",
    " ▄██████   ██████▄▄▄▄",
    "▟█▛   ▜██▄██▛   ▜██▄▄",
    "▜█▙   ▟██▀██▙   ▟██▄▄",
    " ▀█████▀   ▀█████▀",
)


def welcome(master, expert, mode, cwd=None, color=None, width=None, fast_status=None):
    width = width or shutil.get_terminal_size((80, 24)).columns
    # Retain the color argument for callers; use the terminal foreground only.
    location = str(cwd or Path.cwd())
    home = str(Path.home())
    if location == home or location.startswith(home + os.sep):
        location = "~" + location[len(home):]
    info = ["Loop ROS v" + VERSION, TAGLINE,
            "Master · " + master,
            "Mode · " + mode, "Safety · hardware disabled", location]
    logo_width = max(map(len, LOGO))
    if width < logo_width:
        lines = list(info)
    elif width < 80:
        lines = [*LOGO, "", *info]
    else:
        lines = [art.ljust(logo_width) + "  " + (info[i] if i < len(info) else "")
                 for i, art in enumerate(LOGO)]
    fast_label = {'available': 'available (probe only)',
                  'active': 'active (provider default)',
                  'unknown': 'not confirmed'}.get(fast_status)
    if fast_label:
        lines += ['', '  Fast · ' + fast_label]
    lines += ["", "  Ready. You are talking to Master.",
              "  · /switch setup  Configure API URL and key",
              "  · /switch    Choose a provider and model",
              "  · /scene     Describe a scene to generate in MuJoCo",
              "  · /help      Explore commands, agents and permissions",
              "  Ctrl-D or /exit to leave.", ""]
    return "\n".join(lines)
