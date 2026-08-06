"""Install / repair Triton and SageAttention into ComfyUI Python."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Optional

from .detect import resolve_environment
from .models import EnvSnapshot, WheelPlan
from .wheels import load_matrix, plan_install

LogFn = Callable[[str], None]


def _pip_cmd(python_path: str, *args: str) -> list[str]:
    return [python_path, "-m", "pip", *args]


def stream_command(
    cmd: list[str],
    log: Optional[LogFn] = None,
) -> Iterator[str]:
    """Run a command and yield stdout/stderr lines."""
    if log:
        log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip("\n")
        if log:
            log(text)
        yield text
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {' '.join(cmd)}")


def planned_actions(env: EnvSnapshot, plan: WheelPlan, mode: str) -> list[str]:
    force = mode == "repair"
    actions = [
        f"Target Python: {env.python_path} ({env.environment_type})",
        f"Triton: {plan.triton_package}{plan.triton_constraint}",
    ]
    if plan.strategy == "wheel":
        actions.append(f"SageAttention wheel: {plan.sage_version}")
        actions.append(plan.wheel_url or plan.package_spec)
    elif plan.strategy == "pip_sa2_or_fallback":
        actions.append("Try pip: sageattention==2.2.0 --no-build-isolation")
        actions.append(f"Fallback: {load_matrix()['fallback_pypi']}")
    else:
        actions.append(f"SageAttention fallback: {plan.package_spec}")
    if force:
        actions.append("Mode: repair (force-reinstall)")
    return actions


def install_stack(
    comfy_path: str,
    mode: str = "install",
    dry_run: bool = False,
    log: Optional[LogFn] = None,
) -> dict:
    """Install or repair Triton + SageAttention. Returns result dict."""
    def emit(msg: str) -> None:
        if log:
            log(msg)

    env = resolve_environment(comfy_path)
    if not env.python_path:
        raise RuntimeError("No ComfyUI Python resolved")
    if not env.torch_version or not env.torch_cuda_available:
        raise RuntimeError(
            "CUDA-enabled PyTorch is required in the ComfyUI Python before installing SageAttention."
        )

    plan = plan_install(env)
    actions = planned_actions(env, plan, mode)
    emit("Install plan:")
    for action in actions:
        emit(f"  • {action}")

    if dry_run:
        emit("Dry run only — no packages were changed.")
        return {
            "ok": True,
            "dry_run": True,
            "actions": actions,
            "plan": plan.model_dump(),
            "env": env.model_dump(),
        }

    python = env.python_path
    force = mode == "repair"
    logs: list[str] = []

    def collect(msg: str) -> None:
        logs.append(msg)
        emit(msg)

    # Ensure pip is usable
    for line in stream_command(
        _pip_cmd(python, "install", "--upgrade", "pip", "setuptools", "wheel"),
        log=collect,
    ):
        pass

    # Triton
    triton_spec = f"{plan.triton_package}{plan.triton_constraint}"
    triton_args = ["install"]
    if force:
        triton_args.append("--force-reinstall")
    triton_args.extend([triton_spec])
    collect(f"Installing {triton_spec} …")
    try:
        for _ in stream_command(_pip_cmd(python, *triton_args), log=collect):
            pass
    except RuntimeError as exc:
        # On Linux, plain triton may already satisfy; try unconstrained once
        if plan.triton_package == "triton":
            collect(f"Constrained Triton install failed ({exc}); retrying unconstrained …")
            retry = ["install"]
            if force:
                retry.append("--force-reinstall")
            retry.append("triton")
            for _ in stream_command(_pip_cmd(python, *retry), log=collect):
                pass
        else:
            raise

    # SageAttention
    sage_installed = None
    if plan.strategy == "wheel" and plan.wheel_url:
        collect(f"Installing SageAttention from wheel …")
        args = ["install"]
        if force:
            args.append("--force-reinstall")
        args.append(plan.wheel_url)
        for _ in stream_command(_pip_cmd(python, *args), log=collect):
            pass
        sage_installed = plan.sage_version
    elif plan.strategy == "pip_sa2_or_fallback":
        collect("Trying sageattention==2.2.0 with --no-build-isolation …")
        try:
            args = ["install", "--no-build-isolation"]
            if force:
                args.append("--force-reinstall")
            args.append("sageattention==2.2.0")
            for _ in stream_command(_pip_cmd(python, *args), log=collect):
                pass
            sage_installed = "2.2.0"
        except RuntimeError as exc:
            collect(f"SA 2.2.0 install failed: {exc}")
            fallback = load_matrix()["fallback_pypi"]
            collect(f"Falling back to {fallback} …")
            args = ["install"]
            if force:
                args.append("--force-reinstall")
            args.append(fallback)
            for _ in stream_command(_pip_cmd(python, *args), log=collect):
                pass
            sage_installed = "1.0.6"
    else:
        collect(f"Installing {plan.package_spec} …")
        args = ["install"]
        if force:
            args.append("--force-reinstall")
        args.append(plan.package_spec)
        for _ in stream_command(_pip_cmd(python, *args), log=collect):
            pass
        sage_installed = plan.sage_version

    # Quick import confirmation
    confirm = subprocess.run(
        [
            python,
            "-c",
            "from sageattention import sageattn; import importlib.metadata as m;\n"
            "print(m.version('sageattention'))",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if confirm.returncode != 0:
        raise RuntimeError(
            "Install finished but import still fails:\n"
            f"{confirm.stderr or confirm.stdout}"
        )
    installed_ver = confirm.stdout.strip() or sage_installed
    collect(f"Import OK — sageattention {installed_ver}")

    return {
        "ok": True,
        "dry_run": False,
        "actions": actions,
        "sage_version": installed_ver,
        "plan": plan.model_dump(),
        "env": {
            "comfy_path": env.comfy_path,
            "python_path": env.python_path,
            "environment_type": env.environment_type,
        },
        "log": logs,
    }


def write_launch_helper(comfy_path: str) -> Optional[str]:
    """Create a helper launch script with --use-sage-attention if missing."""
    env = resolve_environment(comfy_path)
    root = Path(env.comfy_path)
    if env.platform.startswith("win"):
        path = root / "run_sage_attention.bat"
        py = env.python_path or "python"
        content = (
            "@echo off\n"
            f'"{py}" "{root / "main.py"}" --use-sage-attention %*\n'
        )
    else:
        path = root / "run_sage_attention.sh"
        py = env.python_path or "python"
        content = (
            "#!/usr/bin/env bash\n"
            f'exec "{py}" "{root / "main.py"}" --use-sage-attention "$@"\n'
        )
    path.write_text(content, encoding="utf-8")
    if not env.platform.startswith("win"):
        path.chmod(path.stat().st_mode | 0o111)
    return str(path)
