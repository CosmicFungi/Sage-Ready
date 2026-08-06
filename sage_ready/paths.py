"""Shared path normalization and validation helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator


def strip_comfy_path(value: str) -> str:
    if value is None:
        raise ValueError("ComfyUI path is required")
    cleaned = str(value).strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Enter the path to your ComfyUI folder")
    return cleaned


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
    """Pydantic mixin: strip and validate comfy_path."""

    @field_validator("comfy_path")
    @classmethod
    def _clean_comfy_path(cls, value: str) -> str:
        return strip_comfy_path(value)
