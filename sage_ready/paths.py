"""Shared path normalization and validation helpers."""

from __future__ import annotations

import platform
import re
from pathlib import Path, PureWindowsPath

from pydantic import field_validator

# B:\... or B:/... or \\server\share
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WIN_UNC_RE = re.compile(r"^\\\\[^\\]+\\")


def strip_comfy_path(value: str) -> str:
    if value is None:
        raise ValueError("ComfyUI path is required")
    cleaned = str(value).strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Enter the path to your ComfyUI folder")
    return cleaned


def is_windows_absolute_path(value: str) -> bool:
    text = value.strip().strip('"').strip("'")
    return bool(_WIN_DRIVE_RE.match(text) or _WIN_UNC_RE.match(text))


def looks_like_windows_path(value: str) -> bool:
    """True for drive/UNC paths, or paths that clearly use Windows separators."""
    text = value.strip().strip('"').strip("'")
    if is_windows_absolute_path(text):
        return True
    # Relative Windows-style with backslashes (not a valid Linux absolute path)
    if "\\" in text and not text.startswith("/"):
        return True
    return False


def validate_comfy_path_for_host(value: str) -> str:
    """Strip and reject Windows paths when Sage Ready is not running on Windows."""
    cleaned = strip_comfy_path(value)
    host = platform.system().lower()
    if looks_like_windows_path(cleaned) and not host.startswith("win"):
        raise ValueError(
            "That looks like a Windows ComfyUI path, but Sage Ready is running on "
            f"{platform.system()} and cannot see your B: / C: drives.\n\n"
            "Run Sage Ready on the same Windows PC where ComfyUI is installed:\n"
            "  1. Copy this repo (or download it) onto that PC\n"
            "  2. Open a terminal in the repo folder\n"
            "  3. pip install -r requirements.txt\n"
            "  4. python app.py\n"
            "  5. Paste your ComfyUI folder again "
            "(example: B:\\ComfyUI_windows_portable\\ComfyUI)"
        )
    return cleaned


def normalize_to_path(comfy_path: str) -> Path:
    """Expand/resolve a ComfyUI path for the current OS."""
    cleaned = validate_comfy_path_for_host(comfy_path)
    if platform.system().lower().startswith("win"):
        # Preserve Windows drive letters correctly
        path = Path(str(PureWindowsPath(cleaned))).expanduser()
        try:
            path = path.resolve()
        except OSError:
            pass
    else:
        path = Path(cleaned).expanduser().resolve()
    if path.is_file() and path.name.lower() == "main.py":
        return path.parent
    return path


def path_under_prefix(location: str, prefix: str) -> bool:
    """True if location is prefix itself or a file/dir under prefix."""
    if not location or not prefix:
        return False
    try:
        loc = Path(location).resolve()
        pref = Path(prefix).resolve()
    except OSError:
        loc = Path(location)
        pref = Path(prefix)
    loc_s = str(loc).replace("\\", "/").lower().rstrip("/")
    pref_s = str(pref).replace("\\", "/").lower().rstrip("/")
    return loc_s == pref_s or loc_s.startswith(pref_s + "/")


class ComfyPathMixin:
    """Pydantic mixin: strip and validate comfy_path for this host OS."""

    @field_validator("comfy_path")
    @classmethod
    def _clean_comfy_path(cls, value: str) -> str:
        return validate_comfy_path_for_host(value)
