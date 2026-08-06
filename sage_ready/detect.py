"""ComfyUI root and Python interpreter detection."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .models import EnvSnapshot

PROBE_SCRIPT = r"""
import json, sys, platform
out = {
    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    "executable": sys.executable,
    "prefix": sys.prefix,
    "platform": platform.system().lower(),
    "torch_version": None,
    "torch_cuda": None,
    "torch_cuda_available": False,
    "gpu_name": None,
    "triton_version": None,
    "triton_package": None,
    "sageattention_version": None,
    "sageattention_location": None,
    "sageattn_import_ok": False,
    "site_packages": [],
    "pip_ok": False,
}
try:
    import site
    out["site_packages"] = list(site.getsitepackages()) if hasattr(site, "getsitepackages") else []
    usp = getattr(site, "getusersitepackages", None)
    if callable(usp):
        out["site_packages"].append(usp())
except Exception:
    pass
try:
    import torch
    out["torch_version"] = torch.__version__
    out["torch_cuda"] = getattr(torch.version, "cuda", None)
    out["torch_cuda_available"] = bool(torch.cuda.is_available())
    if out["torch_cuda_available"]:
        try:
            out["gpu_name"] = torch.cuda.get_device_name(0)
        except Exception:
            pass
except Exception as e:
    out["torch_error"] = str(e)
try:
    import importlib.metadata as md
    for pkg in ("triton-windows", "triton"):
        try:
            out["triton_version"] = md.version(pkg)
            out["triton_package"] = pkg
            break
        except md.PackageNotFoundError:
            continue
except Exception:
    pass
if out["triton_version"] is None:
    try:
        import triton
        out["triton_version"] = getattr(triton, "__version__", "unknown")
        out["triton_package"] = "triton"
    except Exception as e:
        out["triton_error"] = str(e)
try:
    import importlib.metadata as md
    try:
        out["sageattention_version"] = md.version("sageattention")
    except md.PackageNotFoundError:
        out["sageattention_version"] = None
    import sageattention
    out["sageattention_location"] = getattr(sageattention, "__file__", None)
    from sageattention import sageattn  # noqa: F401
    out["sageattn_import_ok"] = True
except Exception as e:
    out["sage_error"] = str(e)
    out["sageattn_import_ok"] = False
try:
    import pip  # noqa: F401
    out["pip_ok"] = True
except Exception:
    out["pip_ok"] = False
print(json.dumps(out))
"""


def normalize_comfy_path(comfy_path: str) -> Path:
    path = Path(comfy_path).expanduser().resolve()
    if path.is_file() and path.name.lower() == "main.py":
        return path.parent
    return path


def find_main_py(comfy_root: Path) -> Optional[Path]:
    candidate = comfy_root / "main.py"
    if candidate.is_file():
        return candidate
    nested = comfy_root / "ComfyUI" / "main.py"
    if nested.is_file():
        return nested
    return None


def _has_torch(python_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import torch; print(torch.__version__)"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _candidate_pythons(comfy_root: Path, main_py: Path) -> list[tuple[str, Path, int]]:
    """Return (environment_type, python_path, priority) — lower priority wins.

    Priority bands:
      0 = portable python_embeded next to ComfyUI
      1 = .venv / venv next to ComfyUI
      2 = VIRTUAL_ENV / CONDA_PREFIX (active shells — risky for wrong-env)
      3 = system / current interpreter (last resort)
    """
    candidates: list[tuple[str, Path, int]] = []
    system = platform.system().lower()
    roots = [comfy_root, main_py.parent, main_py.parent.parent]
    seen: set[Path] = set()

    def add(env_type: str, path: Path, priority: int) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if not resolved.is_file() or resolved in seen:
            return
        seen.add(resolved)
        candidates.append((env_type, resolved, priority))

    for root in roots:
        if system == "windows":
            for p in (
                root / "python_embeded" / "python.exe",
                root / "python_embedded" / "python.exe",
                root.parent / "python_embeded" / "python.exe",
                root.parent / "python_embedded" / "python.exe",
            ):
                add("portable", p, 0)
            for name in (".venv", "venv"):
                for base in (root, root.parent):
                    add("venv", base / name / "Scripts" / "python.exe", 1)
        else:
            for name in (".venv", "venv"):
                for base in (root, root.parent):
                    add("venv", base / name / "bin" / "python", 1)

    for env_var, env_type in (("VIRTUAL_ENV", "venv"), ("CONDA_PREFIX", "conda")):
        prefix = os.environ.get(env_var)
        if not prefix:
            continue
        if system == "windows":
            p = Path(prefix) / "python.exe"
            if not p.is_file():
                p = Path(prefix) / "Scripts" / "python.exe"
        else:
            p = Path(prefix) / "bin" / "python"
        # Active env is priority 2 — never preferred over portable
        add(env_type if env_type != "venv" else "active_venv", p, 2)

    add("system", Path(sys.executable), 3)
    candidates.sort(key=lambda row: row[2])
    return candidates


def resolve_python(comfy_root: Path, main_py: Path) -> tuple[str, Path, bool]:
    """Return (environment_type, python_path, is_fallback).

    is_fallback True means we used conda/active/system instead of portable/venv.
    """
    candidates = _candidate_pythons(comfy_root, main_py)
    if not candidates:
        raise FileNotFoundError(
            "Could not find a Python interpreter for this ComfyUI folder. "
            "Expected python_embeded/python.exe (portable) or a .venv beside ComfyUI."
        )

    # Prefer local portable/venv that already has torch
    for env_type, python_path, priority in candidates:
        if priority <= 1 and _has_torch(python_path):
            return env_type, python_path, False

    # Local portable/venv without torch — still better than foreign envs
    for env_type, python_path, priority in candidates:
        if priority <= 1:
            return env_type, python_path, False

    # Fallback: active/system with torch
    for env_type, python_path, priority in candidates:
        if _has_torch(python_path):
            return env_type, python_path, True

    env_type, python_path, _ = candidates[0]
    return env_type, python_path, True


def run_probe(python_path: Path, timeout: int = 60) -> dict:
    result = subprocess.run(
        [str(python_path), "-c", PROBE_SCRIPT],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not inspect ComfyUI’s Python "
            f"({python_path}). Details:\n{result.stderr or result.stdout}"
        )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(
            f"ComfyUI Python probe returned no data:\n{result.stdout}\n{result.stderr}"
        )
    return json.loads(lines[-1])


def nvidia_smi_info() -> tuple[Optional[str], Optional[str]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        first = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        if len(parts) >= 2:
            return parts[0], parts[1]
        if parts:
            return parts[0], None
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    return None, None


def find_launch_scripts(comfy_root: Path, main_py: Path) -> list[str]:
    scripts: list[str] = []
    search_roots = {comfy_root, main_py.parent, main_py.parent.parent}
    patterns = ("*.bat", "*.ps1", "*.sh", "*.cmd")
    for root in search_roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_file():
                    scripts.append(str(path))
    return sorted(set(scripts))


def launch_scripts_have_sage_flag(scripts: list[str]) -> bool:
    flag_re = re.compile(r"--use-sage-attention\b")
    for script in scripts:
        try:
            text = Path(script).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if flag_re.search(text):
            return True
    return False


def resolve_environment(comfy_path: str) -> EnvSnapshot:
    root = normalize_comfy_path(comfy_path)
    if not root.exists():
        raise FileNotFoundError(
            f"That path does not exist: {root}. "
            "Choose your ComfyUI folder (the one with main.py)."
        )

    main_py = find_main_py(root)
    if main_py is None:
        raise FileNotFoundError(
            f"No main.py found under {root}. "
            "Point to your ComfyUI folder — portable root or the inner ComfyUI folder both work."
        )

    comfy_root = main_py.parent
    env_type, python_path, is_fallback = resolve_python(root, main_py)
    # Also try resolving strictly against the folder that holds main.py
    if is_fallback:
        try:
            alt_type, alt_path, alt_fallback = resolve_python(comfy_root, main_py)
            if not alt_fallback:
                env_type, python_path, is_fallback = alt_type, alt_path, alt_fallback
        except FileNotFoundError:
            pass

    probe = run_probe(python_path)
    gpu_name, driver = nvidia_smi_info()
    scripts = find_launch_scripts(root, main_py)

    display_type = env_type
    if is_fallback and env_type in {"system", "conda", "active_venv"}:
        display_type = f"{env_type} (fallback)"

    return EnvSnapshot(
        comfy_path=str(comfy_root),
        main_py=str(main_py),
        python_path=str(python_path),
        python_prefix=probe.get("prefix"),
        environment_type=display_type,
        python_is_fallback=is_fallback,
        python_version=probe.get("python_version") or "",
        platform=probe.get("platform") or platform.system().lower(),
        torch_version=probe.get("torch_version"),
        torch_cuda=probe.get("torch_cuda"),
        torch_cuda_available=bool(probe.get("torch_cuda_available")),
        gpu_name=probe.get("gpu_name") or gpu_name,
        driver_version=driver,
        triton_version=probe.get("triton_version"),
        sageattention_version=probe.get("sageattention_version"),
        sageattention_location=probe.get("sageattention_location"),
        site_packages=[str(p) for p in (probe.get("site_packages") or [])],
        pip_ok=bool(probe.get("pip_ok")),
        has_use_sage_flag=launch_scripts_have_sage_flag(scripts),
        launch_scripts=scripts,
    )
