"""Version comparison helpers for SageAttention readiness."""

from __future__ import annotations

import re
from typing import Optional

# pip/wheel local versions look like:
#   2.2.0+cu130torch2.10.0andhigher.post6
# which must compare equal to plan version:
#   2.2.0.post6
_WHEEL_LOCAL_POST_RE = re.compile(
    r"^(?P<base>\d+\.\d+\.\d+)\+.*\.post(?P<post>\d+)\s*$",
    re.IGNORECASE,
)
_PLAIN_POST_RE = re.compile(r"^(?P<base>\d+\.\d+\.\d+)\.post(?P<post>\d+)\s*$", re.I)
_PLAIN_RE = re.compile(r"^(?P<base>\d+\.\d+\.\d+)\s*$")


def normalize_sage_version(version: str) -> str:
    """Normalize pip/wheel version strings to a comparable SageAttention form."""
    v = version.strip()
    if not v:
        return v

    m = _PLAIN_POST_RE.match(v)
    if m:
        return f"{m.group('base')}.post{m.group('post')}"

    m = _WHEEL_LOCAL_POST_RE.match(v)
    if m:
        return f"{m.group('base')}.post{m.group('post')}"

    m = _PLAIN_RE.match(v.split("+", 1)[0])
    if m:
        return m.group("base")

    # Last resort: strip local label
    return v.split("+", 1)[0]


def parse_version_tuple(version: str) -> tuple[int, ...]:
    """Parse versions like 2.2.0.post6, 1.0.6, or wheel local tags into tuples."""
    normalized = normalize_sage_version(version)
    parts: list[int] = []
    for chunk in re.split(r"[.-]", normalized):
        if chunk.startswith("post") and chunk[4:].isdigit():
            parts.append(int(chunk[4:]))
        elif chunk.isdigit():
            parts.append(int(chunk))
        else:
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


def versions_equivalent(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return normalize_sage_version(a) == normalize_sage_version(b)
