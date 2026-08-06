"""Readiness checklist against a resolved ComfyUI environment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .detect import resolve_environment, run_probe
from .kernel import KERNEL_SCRIPT
from .models import CheckItem, CheckStatus, EnvSnapshot, ScanResponse, WheelPlan
from .paths import path_under_prefix
from .wheels import (
    is_known_bad_version,
    needs_version_upgrade,
    plan_install,
    preferred_sa_version,
)


def _check(
    id_: str,
    title: str,
    status: CheckStatus,
    detail: str = "",
    fix_hint: str = "",
) -> CheckItem:
    return CheckItem(id=id_, title=title, status=status, detail=detail, fix_hint=fix_hint)


def _parse_json_line(stdout: str) -> dict | None:
    """Return the last fully-parseable JSON object printed by a probe."""
    candidates = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
    for line in reversed(candidates):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def package_in_target_env(location: str, env: EnvSnapshot) -> bool:
    """True only if the package lives under this interpreter's prefix or site-packages."""
    prefixes: list[str] = []
    if env.python_prefix:
        prefixes.append(env.python_prefix)
    for sp in env.site_packages:
        if sp:
            prefixes.append(sp)
    # Also accept the interpreter directory (portable embed layouts)
    if env.python_path:
        prefixes.append(str(Path(env.python_path).parent))

    for prefix in prefixes:
        if path_under_prefix(location, prefix):
            return True
    return False


def build_checks(env: EnvSnapshot, plan: WheelPlan, probe: dict | None = None) -> list[CheckItem]:
    checks: list[CheckItem] = []

    if env.main_py and Path(env.main_py).is_file():
        checks.append(
            _check(
                "comfy_root",
                "ComfyUI folder",
                CheckStatus.OK,
                f"Found {env.main_py}",
            )
        )
    else:
        checks.append(
            _check(
                "comfy_root",
                "ComfyUI folder",
                CheckStatus.FAIL,
                "main.py not found",
                "Select the ComfyUI directory that contains main.py "
                "(portable root or the inner ComfyUI folder both work).",
            )
        )

    if env.python_path and Path(env.python_path).exists():
        if env.python_is_fallback:
            checks.append(
                _check(
                    "python",
                    "ComfyUI Python",
                    CheckStatus.WARN,
                    (
                        f"Using {env.environment_type}: {env.python_path} "
                        f"(Python {env.python_version}). "
                        "This is not ComfyUI's portable/venv Python -- "
                        "packages may install into the wrong place."
                    ),
                    "Prefer ComfyUI portable (python_embeded) or a .venv inside the ComfyUI folder.",
                )
            )
        else:
            checks.append(
                _check(
                    "python",
                    "ComfyUI Python",
                    CheckStatus.OK,
                    f"{env.environment_type}: {env.python_path} (Python {env.python_version})",
                )
            )
    else:
        checks.append(
            _check(
                "python",
                "ComfyUI Python",
                CheckStatus.FAIL,
                "No interpreter found for this ComfyUI folder",
                "Use ComfyUI portable (python_embeded) or create a .venv inside ComfyUI.",
            )
        )

    if env.gpu_name or env.driver_version:
        checks.append(
            _check(
                "nvidia_gpu",
                "NVIDIA GPU",
                CheckStatus.OK,
                f"{env.gpu_name or 'GPU detected'}"
                + (f" · driver {env.driver_version}" if env.driver_version else ""),
            )
        )
    else:
        checks.append(
            _check(
                "nvidia_gpu",
                "NVIDIA GPU",
                CheckStatus.FAIL,
                "No NVIDIA GPU reported by nvidia-smi",
                "Install current NVIDIA drivers and confirm nvidia-smi works in a terminal.",
            )
        )

    if not env.torch_version:
        checks.append(
            _check(
                "torch",
                "PyTorch (CUDA)",
                CheckStatus.FAIL,
                "PyTorch is not installed in this Python",
                "Install a CUDA build of PyTorch into ComfyUI's Python "
                "(not a CPU-only `pip install torch`), then scan again.",
            )
        )
    elif not env.torch_cuda_available:
        checks.append(
            _check(
                "torch",
                "PyTorch (CUDA)",
                CheckStatus.FAIL,
                f"PyTorch {env.torch_version} is present but CUDA is not available "
                "(CPU builds cannot run SageAttention).",
                "Reinstall a CUDA-enabled PyTorch wheel that matches your GPU driver.",
            )
        )
    else:
        checks.append(
            _check(
                "torch",
                "PyTorch (CUDA)",
                CheckStatus.OK,
                f"{env.torch_version} · CUDA {env.torch_cuda or '?'} · {env.gpu_name or 'GPU'}",
            )
        )

    if plan.strategy == "wheel":
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention package",
                CheckStatus.OK,
                plan.notes,
            )
        )
    elif plan.strategy == "pip_sa2_or_fallback":
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention package",
                CheckStatus.WARN,
                plan.notes,
                "If the install log shows compiler errors, keep the 1.0.6 fallback "
                "or install the CUDA toolkit, then Repair.",
            )
        )
    else:
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention package",
                CheckStatus.WARN,
                plan.notes,
                "Upgrade PyTorch/CUDA for SageAttention 2.x, or continue with the 1.0.6 fallback.",
            )
        )

    if env.triton_version:
        checks.append(
            _check(
                "triton",
                "Triton",
                CheckStatus.OK,
                f"Installed {env.triton_version}",
            )
        )
    else:
        checks.append(
            _check(
                "triton",
                "Triton",
                CheckStatus.FAIL,
                "Triton is not available in ComfyUI's Python",
                "SageAttention 2.x needs Triton. Click Install & Fix "
                "(uses triton-windows on Windows).",
            )
        )

    sage_ok = False
    sage_detail = ""
    if probe is not None:
        sage_ok = bool(probe.get("sageattn_import_ok"))
        if sage_ok:
            loc = probe.get("sageattention_location") or env.sageattention_location or ""
            ver = env.sageattention_version or "unknown"
            sage_detail = f"Import OK · {ver}"
            if loc:
                sage_detail += f" · {loc}"
        else:
            err = probe.get("sage_error") or "SageAttention import failed"
            sage_detail = err
    elif env.sageattention_version and env.sageattention_location:
        sage_ok = True
        sage_detail = f"{env.sageattention_version} · {env.sageattention_location}"
    else:
        sage_detail = "SageAttention is not installed (or import failed) in ComfyUI's Python"

    if sage_ok:
        status = CheckStatus.OK
        fix = ""
        if is_known_bad_version(env.sageattention_version):
            status = CheckStatus.WARN
            fix = (
                "This SageAttention build is known to produce black or noisy images in ComfyUI. "
                f"Click Repair to upgrade to a safer build ({preferred_sa_version()}+)."
            )
            sage_detail += " · known problematic build"
        elif needs_version_upgrade(env, plan):
            status = CheckStatus.WARN
            fix = (
                f"A better match is available ({plan.sage_version}). "
                "Click Repair to upgrade before using ComfyUI nodes."
            )
            sage_detail += f" · upgrade available → {plan.sage_version}"
        checks.append(
            _check("sageattention", "SageAttention import", status, sage_detail, fix)
        )
    else:
        checks.append(
            _check(
                "sageattention",
                "SageAttention import",
                CheckStatus.FAIL,
                sage_detail,
                "Click Install & Fix to install SageAttention into this exact ComfyUI Python.",
            )
        )

    # Version preference explicit check when import works
    if sage_ok and plan.strategy == "wheel":
        if needs_version_upgrade(env, plan) or is_known_bad_version(env.sageattention_version):
            checks.append(
                _check(
                    "sa_version",
                    "SageAttention version",
                    CheckStatus.WARN,
                    (
                        f"Installed {env.sageattention_version or 'unknown'}; "
                        f"recommended for your stack: {plan.sage_version}."
                    ),
                    "Click Repair so ComfyUI nodes use the recommended wheel.",
                )
            )
        else:
            checks.append(
                _check(
                    "sa_version",
                    "SageAttention version",
                    CheckStatus.OK,
                    f"{env.sageattention_version} matches the recommended wheel plan.",
                )
            )
    else:
        checks.append(
            _check(
                "sa_version",
                "SageAttention version",
                CheckStatus.SKIP,
                "Checked after SageAttention imports successfully.",
            )
        )

    if sage_ok and env.python_path:
        if env.sageattention_location and package_in_target_env(
            env.sageattention_location, env
        ):
            checks.append(
                _check(
                    "package_location",
                    "Installed into ComfyUI's Python",
                    CheckStatus.OK,
                    env.sageattention_location,
                )
            )
        elif env.sageattention_location:
            checks.append(
                _check(
                    "package_location",
                    "Installed into ComfyUI's Python",
                    CheckStatus.FAIL,
                    (
                        f"SageAttention was found at {env.sageattention_location}, "
                        f"which does not look like ComfyUI's Python ({env.python_path}). "
                        "This is the most common cause of 'module not found' in ComfyUI."
                    ),
                    "Click Repair to force-reinstall into the resolved ComfyUI Python.",
                )
            )
        else:
            checks.append(
                _check(
                    "package_location",
                    "Installed into ComfyUI's Python",
                    CheckStatus.FAIL,
                    "SageAttention imports, but its install path could not be verified.",
                    "Click Repair to force-reinstall into the resolved ComfyUI Python.",
                )
            )
    else:
        checks.append(
            _check(
                "package_location",
                "Installed into ComfyUI's Python",
                CheckStatus.SKIP,
                "Checked after SageAttention imports successfully.",
                "Install & Fix, then scan again.",
            )
        )

    if env.has_use_sage_flag:
        checks.append(
            _check(
                "launch_flag",
                "ComfyUI launch flag",
                CheckStatus.OK,
                "A launch script already includes --use-sage-attention",
            )
        )
    else:
        checks.append(
            _check(
                "launch_flag",
                "ComfyUI launch flag",
                CheckStatus.WARN,
                "ComfyUI will not use SageAttention unless you start it with --use-sage-attention.",
                "When you reach Ready, copy the launch command or use the helper script "
                "in your ComfyUI folder. Restart ComfyUI if it is already open.",
            )
        )

    return checks


def run_kernel_check(python_path: str) -> CheckItem:
    try:
        result = subprocess.run(
            [python_path, "-c", KERNEL_SCRIPT],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _check(
            "kernel_test",
            "GPU attention test",
            CheckStatus.FAIL,
            "GPU attention test timed out",
            "Check GPU drivers, click Repair, then Test GPU again.",
        )
    except OSError as exc:
        return _check(
            "kernel_test",
            "GPU attention test",
            CheckStatus.FAIL,
            str(exc),
            "Confirm the ComfyUI Python path is correct.",
        )

    data = _parse_json_line(result.stdout)
    if data is None:
        return _check(
            "kernel_test",
            "GPU attention test",
            CheckStatus.FAIL,
            result.stderr or result.stdout or "No result from GPU attention test",
            "Click Install & Fix, then Test GPU.",
        )

    if data.get("skipped"):
        return _check(
            "kernel_test",
            "GPU attention test",
            CheckStatus.SKIP,
            data.get("detail") or "Skipped -- no GPU",
            "Connect an NVIDIA GPU; Ready cannot complete without this test.",
        )
    if data.get("ok"):
        return _check(
            "kernel_test",
            "GPU attention test",
            CheckStatus.OK,
            data.get("detail") or "Passed",
        )
    return _check(
        "kernel_test",
        "GPU attention test",
        CheckStatus.FAIL,
        data.get("detail") or "GPU attention test failed",
        "Repair SageAttention (prefer 2.2.0.post6+), then Test GPU again.",
    )


def summarize(checks: list[CheckItem], env: EnvSnapshot | None = None) -> tuple[bool, bool, str]:
    """Return (ready_for_install, ready, summary)."""
    by_id = {c.id: c for c in checks}
    blocking = ("comfy_root", "python", "torch")
    ready_for_install = all(
        i in by_id and by_id[i].status in (CheckStatus.OK, CheckStatus.WARN)
        for i in blocking
    )
    must_ok = (
        "comfy_root",
        "nvidia_gpu",
        "torch",
        "triton",
        "sageattention",
        "package_location",
        "kernel_test",
    )
    ready = all(i in by_id and by_id[i].status == CheckStatus.OK for i in must_ok)
    if ready:
        py = by_id.get("python")
        if py is None or py.status == CheckStatus.FAIL:
            ready = False
        if by_id.get("sa_version") and by_id["sa_version"].status == CheckStatus.WARN:
            ready = False
        if env and env.python_is_fallback:
            ready = False

    needs_repair = any(
        c.id in {"sageattention", "sa_version", "package_location"}
        and c.status in (CheckStatus.WARN, CheckStatus.FAIL)
        for c in checks
    )
    if env is not None:
        env.needs_repair = needs_repair

    fails = [c for c in checks if c.status == CheckStatus.FAIL]
    warns = [c for c in checks if c.status == CheckStatus.WARN]
    blocking_skips = [
        c
        for c in checks
        if c.status == CheckStatus.SKIP
        and c.id
        in {
            "nvidia_gpu",
            "package_location",
            "kernel_test",
            "triton",
            "sageattention",
        }
    ]
    if ready:
        summary = "SageAttention is installed and proven ready for ComfyUI."
    elif fails:
        summary = (
            f"{len(fails)} issue(s) need fixing before ComfyUI can use SageAttention safely."
        )
    elif blocking_skips:
        summary = (
            "Scan incomplete -- finish Install & Fix, then Test GPU before ComfyUI can be Ready."
        )
    elif warns:
        summary = (
            "Almost ready -- review the warnings below. "
            "Use Repair if SageAttention is the wrong build or landed in the wrong Python."
        )
    else:
        summary = "Scan complete."

    return ready_for_install, ready, summary


def scan_environment(comfy_path: str, include_kernel: bool = True) -> ScanResponse:
    try:
        env = resolve_environment(comfy_path)
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        return ScanResponse(ok=False, error=str(exc), summary=str(exc))

    plan = plan_install(env)
    probe = None
    if env.python_path:
        try:
            probe = run_probe(Path(env.python_path))
            env.python_prefix = probe.get("prefix") or env.python_prefix
            env.site_packages = [str(p) for p in (probe.get("site_packages") or [])]
            env.pip_ok = bool(probe.get("pip_ok"))
            env.triton_version = probe.get("triton_version") or env.triton_version
            env.sageattention_version = (
                probe.get("sageattention_version") or env.sageattention_version
            )
            env.sageattention_location = (
                probe.get("sageattention_location") or env.sageattention_location
            )
            env.torch_version = probe.get("torch_version") or env.torch_version
            env.torch_cuda = probe.get("torch_cuda") or env.torch_cuda
            env.torch_cuda_available = bool(
                probe.get("torch_cuda_available", env.torch_cuda_available)
            )
            env.gpu_name = probe.get("gpu_name") or env.gpu_name
            env.python_version = probe.get("python_version") or env.python_version
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            probe = None

    # Refresh plan after probe may have filled torch versions
    plan = plan_install(env)
    checks = build_checks(env, plan, probe=probe)

    if include_kernel and env.python_path and any(
        c.id == "sageattention" and c.status in (CheckStatus.OK, CheckStatus.WARN)
        for c in checks
    ):
        checks.append(run_kernel_check(env.python_path))
    else:
        checks.append(
            _check(
                "kernel_test",
                "GPU attention test",
                CheckStatus.SKIP,
                "Skipped until SageAttention imports successfully",
                "Install & Fix first, then Test GPU.",
            )
        )

    ready_for_install, ready, summary = summarize(checks, env)
    return ScanResponse(
        ok=True,
        env=env,
        wheel_plan=plan,
        checks=checks,
        ready_for_install=ready_for_install,
        ready=ready,
        summary=summary,
    )
