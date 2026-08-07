"""Guard: Sage Ready is a local desktop app — refuse Cursor/cloud agent hosts."""

from __future__ import annotations

import os
import platform
import socket
from pathlib import Path
from typing import Optional


CLOUD_REFUSE_MESSAGE = """
Sage Ready is a LOCAL app. It will not run in Cursor Cloud / remote Linux agents.

That environment cannot see your real ComfyUI folder.

On the PC where ComfyUI is installed:
  1. Download branch ZIP:
     https://github.com/CosmicFungi/MyLab/tree/cursor/sage-ready-linux-ecca
  2. Extract, open a terminal in the folder that contains app.py
  3. pip install -r requirements.txt   (Windows: py -m pip install -r requirements.txt)
  4. python app.py                     (Windows: py app.py)
  5. Open ONLY http://127.0.0.1:8765
  6. Paste your ComfyUI folder
     Linux example: /home/you/ComfyUI
     Windows example: B:\\ComfyUI_windows_portable\\ComfyUI
""".strip()


def cloud_block_reason() -> Optional[str]:
    """Return a human reason if this process looks like a cloud/agent host."""
    if os.environ.get("SAGE_READY_ALLOW_CLOUD", "").strip() in {"1", "true", "yes"}:
        return None

    if os.environ.get("CURSOR_AGENT", "").strip() in {"1", "true", "yes"}:
        return "CURSOR_AGENT is set (Cursor Cloud / agent environment)"

    if os.environ.get("CURSOR_CONVERSATION_ID"):
        return "CURSOR_CONVERSATION_ID is set (Cursor agent environment)"

    host = socket.gethostname().lower()
    cwd = Path.cwd().as_posix().lower()
    if host in {"cursor", "cursor-agent"} and (
        cwd == "/workspace" or cwd.startswith("/workspace/")
    ):
        return f"hostname={host!r} cwd={cwd!r} looks like Cursor Cloud"

    # Common cloud agent layout
    if cwd == "/workspace" and Path("/tmp/cursor").is_dir():
        if os.environ.get("CURSOR_AGENT_SOCKET") or Path("/run/cursor").exists():
            return "Cursor agent socket/layout detected under /workspace"

    return None


def assert_local_runtime() -> None:
    """Raise SystemExit if Sage Ready should not start here."""
    reason = cloud_block_reason()
    if reason:
        raise SystemExit(
            f"Refusing to start on a cloud/agent host ({reason}).\n\n{CLOUD_REFUSE_MESSAGE}"
        )


def assert_localhost_bind(host: str) -> None:
    """Only allow loopback binds — this app is not a network service."""
    allowed = {"127.0.0.1", "localhost", "::1"}
    if host.strip().lower() not in allowed:
        raise SystemExit(
            f"Refusing to bind to {host!r}. Sage Ready is local-only.\n"
            "Use the default: python app.py\n"
            "Then open http://127.0.0.1:8765"
        )


def runtime_info() -> dict:
    """Public runtime snapshot — never include PC hostname or local paths."""
    system = platform.system()
    blocked = cloud_block_reason()
    return {
        "platform": system,
        "is_windows": system.lower().startswith("win"),
        "cloud_blocked": blocked is not None,
        "cloud_block_reason": blocked,
        "local_only": True,
    }
