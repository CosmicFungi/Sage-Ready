"""Wheel matrix matching for SageAttention + Triton."""

from __future__ import annotations

import json
import platform
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .models import EnvSnapshot, WheelPlan
from .versioning import (
    normalize_sage_version,
    parse_version_tuple,
    version_less_than,
    versions_equivalent,
)

MATRIX_PATH = Path(__file__).with_name("wheels_matrix.json")
BASE_RELEASE_URL = "https://github.com/woct0rdho/SageAttention/releases/download"
ALLOWED_WHEEL_HOSTS = frozenset({"github.com", "objects.githubusercontent.com"})
ALLOWED_WHEEL_PREFIXES = (
    "https://github.com/woct0rdho/SageAttention/releases/download/",
)


@lru_cache(maxsize=1)
def load_matrix() -> dict[str, Any]:
    with MATRIX_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_torch_version(torch_version: str) -> tuple[str, str, Optional[str]]:
    """Return (full_no_local, major.minor, cuda_code like '128')."""
    raw = torch_version.strip()
    local = ""
    if "+" in raw:
        raw, local = raw.split("+", 1)
    parts = raw.split(".")
    major_minor = ".".join(parts[:2]) if len(parts) >= 2 else raw
    cuda_code = None
    m = re.search(r"cu(\d+)", local, re.I)
    if m:
        cuda_code = m.group(1)
    return raw, major_minor, cuda_code


def cuda_code_from_env(env: EnvSnapshot) -> Optional[str]:
    if env.torch_version:
        _, _, from_torch = parse_torch_version(env.torch_version)
        if from_torch:
            return from_torch
    if env.torch_cuda:
        parts = env.torch_cuda.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}{parts[1]}"
        if len(parts) == 1 and parts[0].isdigit():
            return parts[0]
    return None


def python_tag(python_version: str) -> Optional[str]:
    parts = [p for p in python_version.split(".") if p]
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return f"{parts[0]}{parts[1]}"


def _abi3_floor(py_spec: Optional[str]) -> tuple[str, int]:
    if py_spec is None:
        return "cp39", 39
    return f"cp{py_spec}", int(py_spec)


def _cuda_matches(wheel_cuda: str, detected: str, aliases: dict[str, str]) -> bool:
    if wheel_cuda == detected:
        return True
    return aliases.get(detected) == wheel_cuda


def build_wheel_url(entry: dict[str, Any]) -> str:
    sage_ver = entry["sage_ver"]
    cuda = entry["cuda"]
    tag = entry["tag"]
    abi3 = entry.get("abi3", True)
    py_spec = entry.get("py_spec")
    torch_filename_ver = entry.get("torch_filename_ver")
    torch_pattern = entry["torch_pattern"]

    if abi3:
        sage_base = sage_ver.split(".post")[0] if ".post" in sage_ver else sage_ver
        post_suffix = ""
        if ".post" in sage_ver:
            post_suffix = sage_ver[sage_ver.find(".post") :]
        if torch_filename_ver:
            torch_filename = f"{torch_filename_ver}{post_suffix}"
        else:
            torch_filename = f"{torch_pattern}.0{post_suffix}"
        cp_tag, _ = _abi3_floor(py_spec)
        name = (
            f"sageattention-{sage_base}+cu{cuda}torch{torch_filename}"
            f"-{cp_tag}-abi3-win_amd64.whl"
        )
    else:
        name = (
            f"sageattention-{sage_ver}+cu{cuda}torch{torch_pattern}"
            f"-cp{py_spec}-cp{py_spec}-win_amd64.whl"
        )
    return f"{BASE_RELEASE_URL}/{tag}/{name}"


def is_allowed_wheel_url(url: str) -> bool:
    if not url.startswith(ALLOWED_WHEEL_PREFIXES):
        return False
    host = urlparse(url).hostname or ""
    return host in ALLOWED_WHEEL_HOSTS


def triton_constraint_for_torch(torch_version: str) -> str:
    matrix = load_matrix()
    _, major_minor, _ = parse_torch_version(torch_version)
    try:
        major, minor = [int(x) for x in major_minor.split(".")[:2]]
    except ValueError:
        return ">=3.0"
    for row in matrix["triton_constraints"]:
        tmin = row["torch_min"]
        if (major, minor) >= tuple(tmin):
            return row["constraint"]
    return ">=3.0"


def find_matching_wheel(
    env: EnvSnapshot,
    host_platform: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    matrix = load_matrix()
    host = host_platform or platform.system().lower()
    plat_key = "win32" if host.startswith("win") else host

    if not env.torch_version or not env.python_version:
        return None

    torch_full, torch_mm, _ = parse_torch_version(env.torch_version)
    cuda = cuda_code_from_env(env)
    if not cuda:
        return None

    py_tag = python_tag(env.python_version)
    if not py_tag:
        return None
    try:
        py_int = int(py_tag)
    except ValueError:
        return None

    aliases = matrix.get("cuda_aliases", {})
    matches: list[dict[str, Any]] = []

    for entry in matrix["wheels"]:
        platforms = entry.get("platforms") or ["win32"]
        if plat_key not in platforms:
            continue

        if not _cuda_matches(entry["cuda"], cuda, aliases):
            continue

        pattern = entry["torch_pattern"]
        if pattern.count(".") == 2:
            if torch_full != pattern:
                continue
        else:
            if torch_mm != pattern:
                continue

        if entry.get("abi3"):
            _, floor = _abi3_floor(entry.get("py_spec"))
            if py_int < floor:
                continue
        else:
            if entry.get("py_spec") != py_tag:
                continue

        matched = dict(entry)
        matched["wheel_url"] = build_wheel_url(entry)
        matched["detected_cuda"] = cuda
        matched["matched_cuda"] = entry["cuda"]
        matches.append(matched)

    if not matches:
        return None

    # Prefer highest sage_ver using numeric version tuples (post10 > post6)
    matches.sort(key=lambda m: parse_version_tuple(m["sage_ver"]), reverse=True)
    return matches[0]


def preferred_sa_version() -> str:
    return load_matrix().get("preferred_min_sa2", "2.2.0.post6")


def plan_install(env: EnvSnapshot, host_platform: Optional[str] = None) -> WheelPlan:
    host = host_platform or platform.system().lower()
    is_windows = host.startswith("win")
    triton_pkg = "triton-windows" if is_windows else "triton"
    torch_ver = env.torch_version or "0.0.0"
    constraint = triton_constraint_for_torch(torch_ver)
    preferred = preferred_sa_version()

    match = find_matching_wheel(env, host_platform=host)
    if match:
        notes = (
            f"Matching prebuilt SageAttention {match['sage_ver']} "
            f"for CUDA {match['matched_cuda']} / PyTorch {match['torch_pattern']}."
        )
        if match.get("detected_cuda") != match.get("matched_cuda"):
            notes += (
                f" (Your CUDA {match['detected_cuda']} safely uses the "
                f"{match['matched_cuda']} wheel.)"
            )
        if not is_allowed_wheel_url(match["wheel_url"]):
            notes += " Wheel URL failed safety allowlist -- install will be blocked."
        return WheelPlan(
            strategy="wheel",
            sage_version=match["sage_ver"],
            package_spec=match["wheel_url"],
            triton_package=triton_pkg,
            triton_constraint=constraint,
            wheel_url=match["wheel_url"],
            notes=notes,
        )

    matrix = load_matrix()
    if not is_windows:
        return WheelPlan(
            strategy="pip_sa2_or_fallback",
            sage_version=preferred,
            package_spec="sageattention==2.2.0",
            triton_package=triton_pkg,
            triton_constraint=constraint,
            wheel_url=None,
            notes=(
                "On Linux we can't use the Windows prebuilt wheels. "
                "Install & Fix will try SageAttention 2.2.0 from pip "
                "(may need a CUDA toolkit), then fall back to 1.0.6 if the build fails."
            ),
        )

    return WheelPlan(
        strategy="fallback_pypi",
        sage_version="1.0.6",
        package_spec=matrix["fallback_pypi"],
        triton_package=triton_pkg,
        triton_constraint=constraint,
        wheel_url=None,
        notes=(
            "No matching SageAttention 2.x wheel for this Python/PyTorch/CUDA mix. "
            "Install & Fix will use sageattention==1.0.6 "
            "(slower, but usually works without a custom wheel)."
        ),
    )


def is_known_bad_version(version: Optional[str]) -> bool:
    if not version:
        return False
    # Normalize wheel tags like 2.2.0+cu130...post5 → 2.2.0.post5
    normalized = normalize_sage_version(version)
    bad = load_matrix().get("known_bad_versions", [])
    return any(normalized == b for b in bad)


def needs_version_upgrade(env: EnvSnapshot, plan: WheelPlan) -> bool:
    """True when a better planned SA2 wheel exists than what is installed."""
    if plan.strategy != "wheel":
        return is_known_bad_version(env.sageattention_version)
    if is_known_bad_version(env.sageattention_version):
        return True
    if not env.sageattention_version:
        return True
    # 2.2.0+cu130torch2.10.0andhigher.post6 == plan 2.2.0.post6
    if versions_equivalent(env.sageattention_version, plan.sage_version):
        return False
    return version_less_than(env.sageattention_version, plan.sage_version)
