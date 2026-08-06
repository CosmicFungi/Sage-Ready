"""Version comparison helpers for SageAttention readiness."""

from __future__ import annotations

import re
from typing import Optional


def parse_version_tuple(version: str) -> tuple[int, ...]:
    """Parse versions like 2.2.0.post6 or 1.0.6 into comparable tuples."""
    version = version.strip().split("+")[0]
    parts: list[int] = []
    for chunk in re.split(r"[.-]", version):
        if chunk.startswith("post") and chunk[4:].isdigit():
            parts.append(int(chunk[4:]))
        elif chunk.isdigit():
            parts.append(int(chunk))
        else:
            # Non-numeric suffix — stop
            break
    return tuple(parts) if parts else (0,)


def version_at_least(installed: Optional[str], minimum: str) -> bool:
    if not installed:
        return False
    return parse_version_tuple(installed) >= parse_version_tuple(minimum)


def version_less_than(installed: Optional[str], other: str) -> bool:
    if not installed:
        return True
    return parse_version_tuple(installed) < parse_version_tuple(other)
