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
import json, os, sys, platform
out = {
    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    "executable": sys.executable,
    "platform": platform.system().lower(),
    "torch_version": None,
    "torch_cuda": None,
    "torch_cuda_available": False,
    "gpu_name": None,
    "triton_version": None,
    "sageattention_version": None,
    "sageattention_location": None,
    "site_packages": [],
}
try:
    import site
    out["site_packages"] = list(site.getsitepackages()) if hasattr(site, "getsitepackages") else []
    if hasattr(site, "getusersitepackages"):
        out["site_packages"].append(site.getusersitepackages())
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
    # Nested ComfyUI folder (portable zip layouts)
    nested = comfy_root / "ComfyUI" / "main.py"
    if nested.is_file():
        return nested
    return None


def _candidate_pythons(comfy_root: Path, main_py: Path) -> list[tuple[str, Path]]:
    """Return (environment_type, python_path) candidates in priority order."""
    candidates: list[tuple[str, Path]] = []
    system = platform.system().lower()
    roots = [comfy_root, main_py.parent, main_py.parent.parent]

    seen: set[Path] = set()
    for root in roots:
        if system == "windows":
            embedded = [
                root / "python_embeded" / "python.exe",
                root / "python_embedded" / "python.exe",
                root.parent / "python_embeded" / "python.exe",
                root.parent / "python_embedded" / "python.exe",
            ]
            for p in embedded:
                if p.is_file() and p not in seen:
                    candidates.append(("portable", p))
                    seen.add(p)
            for name in (".venv", "venv"):
                for base in (root, root.parent):
                    p = base / name / "Scripts" / "python.exe"
                    if p.is_file() and p not in seen:
                        candidates.append(("venv", p))
                        seen.add(p)
        else:
            for name in (".venv", "venv"):
                for base in (root, root.parent):
                    p = base / name / "bin" / "python"
                    if p.is_file() and p not in seen:
                        candidates.append(("venv", p))
                        seen.add(p)

    # VIRTUAL_ENV / CONDA_PREFIX when they contain torch (likely active Comfy env)
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
        if p.is_file() and p not in seen:
            candidates.append((env_type, p))
            seen.add(p)

    # Last resort: current interpreter (useful for Linux/dev installs)
    current = Path(sys.executable)
    if current.is_file() and current not in seen:
        candidates.append(("system", current))

    return candidates


def resolve_python(comfy_root: Path, main_py: Path) -> tuple[str, Path]:
    candidates = _candidate_pythons(comfy_root, main_py)
    if not candidates:
        raise FileNotFoundError(
            "Could not find a Python interpreter for this ComfyUI folder. "
            "Expected python_embeded/python.exe (portable) or a .venv."
        )

    # Prefer a candidate that already has torch installed
    for env_type, python_path in candidates:
        try:
            result = subprocess.run(
                [str(python_path), "-c", "import torch; print(torch.__version__)"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return env_type, python_path
        except (OSError, subprocess.TimeoutExpired):
            continue

    return candidates[0]


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
            f"Failed to probe interpreter {python_path}:\n{result.stderr or result.stdout}"
        )
    # Probe prints one JSON line; tolerate trailing noise
    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"Probe returned no JSON:\n{result.stdout}\n{result.stderr}")
    return json.loads(lines[-1])


def nvidia_smi_info() -> tuple[Optional[str], Optional[str]]:
    """Return (gpu_name, driver_version) from nvidia-smi if available."""
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
        raise FileNotFoundError(f"Path does not exist: {root}")

    main_py = find_main_py(root)
    if main_py is None:
        raise FileNotFoundError(
            f"No main.py found under {root}. Point to your ComfyUI folder "
            "(the one that contains main.py)."
        )

    # Prefer the directory that actually contains main.py for nested layouts
    comfy_root = main_py.parent
    env_type, python_path = resolve_python(root if root == comfy_root else root, main_py)
    # If nested, also try resolving against comfy_root
    if env_type == "system":
        try:
            env_type, python_path = resolve_python(comfy_root, main_py)
        except FileNotFoundError:
            pass

    probe = run_probe(python_path)
    gpu_name, driver = nvidia_smi_info()
    scripts = find_launch_scripts(root, main_py)

    return EnvSnapshot(
        comfy_path=str(comfy_root),
        main_py=str(main_py),
        python_path=str(python_path),
        environment_type=env_type,
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
        has_use_sage_flag=launch_scripts_have_sage_flag(scripts),
        launch_scripts=scripts,
    )
