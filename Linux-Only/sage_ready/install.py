"""Install / repair Triton and SageAttention into ComfyUI Python."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Optional

from .detect import resolve_environment, run_probe
from .models import EnvSnapshot, WheelPlan
from .wheels import is_allowed_wheel_url, load_matrix, needs_version_upgrade, plan_install

LogFn = Callable[[str], None]
_install_lock = threading.Lock()


def _pip_cmd(python_path: str, *args: str) -> list[str]:
    return [python_path, "-m", "pip", *args]


def stream_command(
    cmd: list[str],
    log: Optional[LogFn] = None,
) -> Iterator[str]:
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
        actions.append("Mode: repair (force-reinstall into ComfyUI's Python)")
    return actions


def _ensure_pip(python: str, log: LogFn) -> None:
    probe = subprocess.run(
        [python, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if probe.returncode == 0:
        log(f"pip OK: {probe.stdout.strip()}")
        return
    log("pip is missing -- trying ensurepip …")
    ensure = subprocess.run(
        [python, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if ensure.returncode != 0:
        raise RuntimeError(
            "This ComfyUI Python has no working pip. "
            "For portable installs, repair python_embeded or run get-pip.py inside it.\n"
            f"{ensure.stderr or ensure.stdout or probe.stderr}"
        )
    log("ensurepip finished")


def _should_force_repair(env: EnvSnapshot, plan: WheelPlan) -> bool:
    """Compute repair need from live env state (do not trust env.needs_repair)."""
    from .checks import package_in_target_env

    if needs_version_upgrade(env, plan) or is_known_bad_needs_force(env):
        return True
    if env.sageattention_location and env.python_path:
        if not package_in_target_env(env.sageattention_location, env):
            return True
    return False


def install_stack(
    comfy_path: str,
    mode: str = "install",
    dry_run: bool = False,
    log: Optional[LogFn] = None,
) -> dict:
    def emit(msg: str) -> None:
        if log:
            log(msg)

    # Dry-runs only plan -- don't block a real install behind the exclusive lock
    if dry_run:
        return _install_stack_locked(comfy_path, mode, True, emit)

    if not _install_lock.acquire(blocking=False):
        raise RuntimeError("Another install is already running. Wait for it to finish.")

    try:
        return _install_stack_locked(comfy_path, mode, False, emit)
    finally:
        _install_lock.release()


def _install_stack_locked(
    comfy_path: str,
    mode: str,
    dry_run: bool,
    emit: LogFn,
) -> dict:
    env = resolve_environment(comfy_path)
    if not env.python_path:
        raise RuntimeError("No ComfyUI Python found")
    if env.python_is_fallback:
        emit(
            "WARNING: Using a fallback Python (not portable/venv). "
            "Packages may not be visible to ComfyUI."
        )
    if not env.torch_version or not env.torch_cuda_available:
        raise RuntimeError(
            "CUDA-enabled PyTorch is required in ComfyUI's Python before installing SageAttention."
        )

    # Refresh probe fields used for location/version decisions
    try:
        probe = run_probe(Path(env.python_path))
        env.python_prefix = probe.get("prefix") or env.python_prefix
        env.site_packages = [str(p) for p in (probe.get("site_packages") or [])]
        env.sageattention_version = (
            probe.get("sageattention_version") or env.sageattention_version
        )
        env.sageattention_location = (
            probe.get("sageattention_location") or env.sageattention_location
        )
    except Exception as exc:  # noqa: BLE001
        emit(f"Pre-install probe note: {exc}")

    plan = plan_install(env)

    # Auto-upgrade to repair when version/location needs force
    effective_mode = mode
    if mode == "install" and _should_force_repair(env, plan):
        effective_mode = "repair"
        emit(
            "Switching to repair mode so the recommended package force-reinstalls "
            "into ComfyUI's Python."
        )

    actions = planned_actions(env, plan, effective_mode)
    emit("Install plan:")
    for action in actions:
        emit(f"  • {action}")

    if dry_run:
        emit("Dry run only -- no packages were changed.")
        return {
            "ok": True,
            "dry_run": True,
            "actions": actions,
            "plan": plan.model_dump(),
            "env": env.model_dump(),
        }

    if plan.strategy == "wheel" and plan.wheel_url and not is_allowed_wheel_url(plan.wheel_url):
        raise RuntimeError(
            "Refusing to download wheel from an unexpected URL. "
            "Only official woct0rdho SageAttention release URLs are allowed."
        )

    python = env.python_path
    force = effective_mode == "repair"
    logs: list[str] = []

    def collect(msg: str) -> None:
        logs.append(msg)
        emit(msg)

    _ensure_pip(python, collect)

    # Mild pip tooling refresh -- skip aggressive self-upgrade failures
    try:
        for _ in stream_command(
            _pip_cmd(python, "install", "--upgrade", "setuptools", "wheel"),
            log=collect,
        ):
            pass
    except RuntimeError as exc:
        collect(f"setuptools/wheel upgrade skipped: {exc}")

    triton_spec = f"{plan.triton_package}{plan.triton_constraint}"
    triton_args = ["install"]
    if force:
        triton_args.append("--force-reinstall")
    triton_args.append(triton_spec)
    collect(f"Installing {triton_spec} …")
    try:
        for _ in stream_command(_pip_cmd(python, *triton_args), log=collect):
            pass
    except RuntimeError as exc:
        if plan.triton_package == "triton":
            collect(f"Constrained Triton install failed ({exc}); retrying unconstrained …")
            retry = ["install"]
            if force:
                retry.append("--force-reinstall")
            retry.append("triton")
            for _ in stream_command(_pip_cmd(python, *retry), log=collect):
                pass
        elif plan.triton_package == "triton-windows":
            collect(f"Constrained triton-windows failed ({exc}); retrying unconstrained …")
            retry = ["install"]
            if force:
                retry.append("--force-reinstall")
            retry.append("triton-windows")
            for _ in stream_command(_pip_cmd(python, *retry), log=collect):
                pass
        else:
            raise

    # Confirm triton import
    triton_check = subprocess.run(
        [python, "-c", "import triton; print(getattr(triton, '__version__', 'ok'))"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if triton_check.returncode != 0:
        raise RuntimeError(
            "Triton installed but still does not import. "
            "On Windows, confirm Visual C++ redistributables are installed.\n"
            f"{triton_check.stderr or triton_check.stdout}"
        )
    collect(f"Triton import OK ({triton_check.stdout.strip()})")

    sage_installed = None
    if plan.strategy == "wheel" and plan.wheel_url:
        collect("Installing SageAttention from the official prebuilt wheel …")
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
            collect(f"SageAttention 2.2.0 build/install failed: {exc}")
            if not env.platform.lower().startswith("win"):
                collect(
                    "Linux note: SageAttention 2.x often needs a matching CUDA toolkit "
                    "(nvcc), a CUDA-enabled PyTorch already in this venv, and build tools. "
                    "Community Hugging Face Linux wheels are not auto-installed. "
                    "Falling back to sageattention==1.0.6 next."
                )
            fallback = load_matrix()["fallback_pypi"]
            collect(f"Falling back to {fallback} (slower, usually works without compiling) …")
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
            "Install finished but SageAttention still does not import in ComfyUI's Python:\n"
            f"{confirm.stderr or confirm.stdout}"
        )
    installed_ver = confirm.stdout.strip() or sage_installed
    collect(f"Import OK -- sageattention {installed_ver}")

    # Refresh location sanity
    try:
        probe = run_probe(Path(python))
        loc = probe.get("sageattention_location")
        if loc:
            collect(f"Package location: {loc}")
    except Exception as exc:  # noqa: BLE001
        collect(f"Post-install probe note: {exc}")

    return {
        "ok": True,
        "dry_run": False,
        "actions": actions,
        "mode": effective_mode,
        "sage_version": installed_ver,
        "plan": plan.model_dump(),
        "env": {
            "comfy_path": env.comfy_path,
            "python_path": env.python_path,
            "environment_type": env.environment_type,
        },
        "log": logs,
    }


def is_known_bad_needs_force(env: EnvSnapshot) -> bool:
    from .wheels import is_known_bad_version

    return is_known_bad_version(env.sageattention_version)


def write_launch_helper(comfy_path: str) -> Optional[str]:
    """Create a helper launch script with --use-sage-attention.

    Existing helpers are backed up to *.bak before overwrite.
    """
    env = resolve_environment(comfy_path)
    root = Path(env.comfy_path)
    is_windows = env.platform.lower().startswith("win")
    if is_windows:
        path = root / "run_sage_attention.bat"
        py = env.python_path or "python"
        content = (
            "@echo off\r\n"
            "echo Starting ComfyUI with SageAttention enabled...\r\n"
            f'"{py}" "{root / "main.py"}" --use-sage-attention %*\r\n'
        )
    else:
        path = root / "run_sage_attention.sh"
        py = env.python_path or "python"
        content = (
            "#!/usr/bin/env bash\n"
            "echo 'Starting ComfyUI with SageAttention enabled...'\n"
            f'exec "{py}" "{root / "main.py"}" --use-sage-attention "$@"\n'
        )
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            bak.write_bytes(path.read_bytes())
        except OSError:
            pass
    path.write_text(content, encoding="utf-8")
    if not is_windows:
        path.chmod(path.stat().st_mode | 0o111)
    return str(path)
