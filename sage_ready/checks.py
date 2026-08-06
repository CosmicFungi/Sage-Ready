"""Readiness checklist against a resolved ComfyUI environment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .detect import resolve_environment, run_probe
from .models import CheckItem, CheckStatus, EnvSnapshot, ScanResponse, WheelPlan
from .wheels import is_known_bad_version, plan_install

KERNEL_PROBE = r"""
import json, sys
result = {"ok": False, "skipped": False, "cosine": None, "dtype": None, "detail": ""}
try:
    import torch
    from sageattention import sageattn
    if not torch.cuda.is_available():
        result["skipped"] = True
        result["detail"] = "No CUDA device available for kernel test"
        print(json.dumps(result))
        sys.exit(0)
    torch.manual_seed(0)
    device = "cuda"
    dtype = torch.float16 if torch.cuda.is_bf16_supported() is False else torch.float16
    # Prefer fp16 for broadest kernel support
    B, H, S, D = 1, 4, 128, 64
    q = torch.randn(B, H, S, D, device=device, dtype=dtype)
    k = torch.randn(B, H, S, D, device=device, dtype=dtype)
    v = torch.randn(B, H, S, D, device=device, dtype=dtype)
    with torch.no_grad():
        out_sage = sageattn(q, k, v, tensor_layout="HND", is_causal=False)
        out_sdpa = torch.nn.functional.scaled_dot_product_attention(q, k, v, is_causal=False)
    a = out_sage.reshape(-1).float()
    b = out_sdpa.reshape(-1).float()
    cosine = torch.nn.functional.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).item()
    result["ok"] = cosine >= 0.99
    result["cosine"] = float(cosine)
    result["dtype"] = str(dtype).replace("torch.", "")
    result["detail"] = f"sageattn vs SDPA cosine={cosine:.5f} (need >= 0.99)"
except Exception as e:
    result["detail"] = f"{type(e).__name__}: {e}"
print(json.dumps(result))
"""


def _check(
    id_: str,
    title: str,
    status: CheckStatus,
    detail: str = "",
    fix_hint: str = "",
) -> CheckItem:
    return CheckItem(id=id_, title=title, status=status, detail=detail, fix_hint=fix_hint)


def build_checks(env: EnvSnapshot, plan: WheelPlan, probe: dict | None = None) -> list[CheckItem]:
    checks: list[CheckItem] = []

    # ComfyUI root
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
                "Select the ComfyUI directory that contains main.py.",
            )
        )

    # Interpreter
    if env.python_path and Path(env.python_path).exists():
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
                "No interpreter resolved",
                "Use ComfyUI portable (python_embeded) or create a .venv inside ComfyUI.",
            )
        )

    # GPU / driver
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
                "nvidia-smi did not report a GPU",
                "Install NVIDIA drivers and confirm nvidia-smi works in a terminal.",
            )
        )

    # Torch + CUDA
    if not env.torch_version:
        checks.append(
            _check(
                "torch",
                "PyTorch (CUDA)",
                CheckStatus.FAIL,
                "torch is not installed in this Python",
                "Install a CUDA build of PyTorch into your ComfyUI Python, then scan again.",
            )
        )
    elif not env.torch_cuda_available:
        checks.append(
            _check(
                "torch",
                "PyTorch (CUDA)",
                CheckStatus.FAIL,
                f"torch {env.torch_version} found but CUDA is not available",
                "Reinstall a CUDA-enabled PyTorch wheel matching your GPU driver.",
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

    # Wheel plan
    if plan.strategy == "wheel":
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention wheel",
                CheckStatus.OK,
                plan.notes,
            )
        )
    elif plan.strategy == "pip_sa2_or_fallback":
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention wheel",
                CheckStatus.WARN,
                plan.notes,
                "On Linux, build tools / CUDA toolkit may be required for SageAttention 2.x.",
            )
        )
    else:
        checks.append(
            _check(
                "wheel_match",
                "Compatible SageAttention wheel",
                CheckStatus.WARN,
                plan.notes,
                "Install & Fix will use SageAttention 1.0.6 fallback, or upgrade Torch/CUDA for SA2.",
            )
        )

    # Triton
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
                "Triton is not importable in ComfyUI Python",
                "Click Install & Fix to install a Torch-compatible Triton package.",
            )
        )

    # SageAttention import
    sage_ok = False
    sage_detail = ""
    if probe is not None:
        sage_ok = bool(probe.get("sageattn_import_ok"))
        if sage_ok:
            loc = probe.get("sageattention_location") or env.sageattention_location or ""
            ver = env.sageattention_version or "unknown"
            sage_detail = f"from sageattention import sageattn OK · {ver}"
            if loc:
                sage_detail += f" · {loc}"
        else:
            sage_detail = probe.get("sage_error") or "sageattention import failed"
    elif env.sageattention_version and env.sageattention_location:
        sage_ok = True
        sage_detail = f"{env.sageattention_version} · {env.sageattention_location}"
    else:
        sage_detail = "sageattention not installed or import failed"

    if sage_ok:
        status = CheckStatus.OK
        fix = ""
        if is_known_bad_version(env.sageattention_version):
            status = CheckStatus.WARN
            fix = (
                "This build (post5) can produce black/noise outputs. "
                "Click Repair to upgrade to post6."
            )
            sage_detail += " · known problematic build"
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
                "Click Install & Fix to install SageAttention into this exact Python.",
            )
        )

    # Package location sanity
    if env.sageattention_location and env.python_path:
        loc = env.sageattention_location.replace("\\", "/").lower()
        py = env.python_path.replace("\\", "/").lower()
        # Heuristic: portable/venv packages should live near the interpreter prefix
        prefix = str(Path(env.python_path).parent).replace("\\", "/").lower()
        parent_prefix = str(Path(env.python_path).parent.parent).replace("\\", "/").lower()
        if prefix in loc or parent_prefix in loc or "site-packages" in loc:
            checks.append(
                _check(
                    "package_location",
                    "Installed into ComfyUI env",
                    CheckStatus.OK,
                    env.sageattention_location,
                )
            )
        else:
            checks.append(
                _check(
                    "package_location",
                    "Installed into ComfyUI env",
                    CheckStatus.WARN,
                    f"Package path looks unusual for {env.python_path}: {env.sageattention_location}",
                    "Use Repair to force-reinstall into the resolved ComfyUI Python.",
                )
            )
    else:
        checks.append(
            _check(
                "package_location",
                "Installed into ComfyUI env",
                CheckStatus.SKIP,
                "Cannot verify package location until sageattention imports.",
                "Install & Fix, then scan again.",
            )
        )

    # Launch flag
    if env.has_use_sage_flag:
        checks.append(
            _check(
                "launch_flag",
                "ComfyUI --use-sage-attention",
                CheckStatus.OK,
                "A launch script already includes --use-sage-attention",
            )
        )
    else:
        checks.append(
            _check(
                "launch_flag",
                "ComfyUI --use-sage-attention",
                CheckStatus.WARN,
                "No launch script found with --use-sage-attention",
                "After Ready, start ComfyUI with: python main.py --use-sage-attention",
            )
        )

    return checks


def run_kernel_check(python_path: str) -> CheckItem:
    try:
        result = subprocess.run(
            [python_path, "-c", KERNEL_PROBE],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _check(
            "kernel_test",
            "Attention kernel smoke test",
            CheckStatus.FAIL,
            "Kernel test timed out",
            "Check GPU drivers and try Repair, then Verify again.",
        )
    except OSError as exc:
        return _check(
            "kernel_test",
            "Attention kernel smoke test",
            CheckStatus.FAIL,
            str(exc),
            "Confirm the ComfyUI Python path is correct.",
        )

    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        return _check(
            "kernel_test",
            "Attention kernel smoke test",
            CheckStatus.FAIL,
            result.stderr or result.stdout or "No result from kernel probe",
            "Click Install & Fix, then Verify.",
        )

    data = json.loads(lines[-1])
    if data.get("skipped"):
        return _check(
            "kernel_test",
            "Attention kernel smoke test",
            CheckStatus.SKIP,
            data.get("detail") or "Skipped",
            "Connect an NVIDIA GPU to run the full readiness proof.",
        )
    if data.get("ok"):
        return _check(
            "kernel_test",
            "Attention kernel smoke test",
            CheckStatus.OK,
            data.get("detail") or "Passed",
        )
    return _check(
        "kernel_test",
        "Attention kernel smoke test",
        CheckStatus.FAIL,
        data.get("detail") or "Kernel mismatch or error",
        "Repair SageAttention (prefer 2.2.0.post6+) and verify again.",
    )


def summarize(checks: list[CheckItem]) -> tuple[bool, bool, str]:
    """Return (ready_for_install, ready, summary)."""
    by_id = {c.id: c for c in checks}
    blocking = ("comfy_root", "python", "torch")
    ready_for_install = all(
        i in by_id and by_id[i].status in (CheckStatus.OK, CheckStatus.WARN)
        for i in blocking
    )

    # Ready requires import + kernel proof. launch_flag may stay WARN.
    must_ok = ("comfy_root", "python", "torch", "triton", "sageattention", "kernel_test")
    ready = all(
        i in by_id and by_id[i].status == CheckStatus.OK
        for i in must_ok
    )

    fails = [c for c in checks if c.status == CheckStatus.FAIL]
    warns = [c for c in checks if c.status == CheckStatus.WARN]
    if ready:
        summary = "SageAttention is installed and proven ready for ComfyUI."
    elif fails:
        summary = f"{len(fails)} issue(s) need fixing before ComfyUI can use SageAttention."
    elif warns:
        summary = "Environment looks usable, but warnings remain — Repair recommended."
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
            # Refresh sage fields from fresh probe
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

    checks = build_checks(env, plan, probe=probe)

    if include_kernel and env.python_path and any(
        c.id == "sageattention" and c.status in (CheckStatus.OK, CheckStatus.WARN) for c in checks
    ):
        checks.append(run_kernel_check(env.python_path))
    else:
        checks.append(
            _check(
                "kernel_test",
                "Attention kernel smoke test",
                CheckStatus.SKIP,
                "Skipped until SageAttention imports successfully",
                "Install & Fix first, then Verify.",
            )
        )

    ready_for_install, ready, summary = summarize(checks)
    return ScanResponse(
        ok=True,
        env=env,
        wheel_plan=plan,
        checks=checks,
        ready_for_install=ready_for_install,
        ready=ready,
        summary=summary,
    )
