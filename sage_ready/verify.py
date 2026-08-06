"""GPU kernel verification for SageAttention."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .detect import resolve_environment
from .models import VerifyResponse

KERNEL_SCRIPT = r"""
import json, sys
result = {"ok": False, "skipped": False, "cosine": None, "dtype": None, "detail": "", "error": None}
try:
    import torch
    from sageattention import sageattn
    if not torch.cuda.is_available():
        result["skipped"] = True
        result["detail"] = "No NVIDIA GPU available — kernel test skipped"
        print(json.dumps(result))
        sys.exit(0)
    torch.manual_seed(0)
    device = "cuda"
    dtype = torch.float16
    B, H, S, D = 1, 4, 128, 64
    q = torch.randn(B, H, S, D, device=device, dtype=dtype)
    k = torch.randn(B, H, S, D, device=device, dtype=dtype)
    v = torch.randn(B, H, S, D, device=device, dtype=dtype)
    with torch.no_grad():
        out_sage = sageattn(q, k, v, tensor_layout="HND", is_causal=False)
        out_sdpa = torch.nn.functional.scaled_dot_product_attention(q, k, v, is_causal=False)
    a = out_sage.reshape(-1).float()
    b = out_sdpa.reshape(-1).float()
    cosine = float(torch.nn.functional.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).item())
    result["cosine"] = cosine
    result["dtype"] = "float16"
    result["ok"] = cosine >= 0.99
    result["detail"] = (
        f"sageattn matches SDPA (cosine {cosine:.5f})"
        if result["ok"]
        else f"cosine {cosine:.5f} below 0.99 — possible bad wheel / black-noise risk"
    )
except Exception as e:
    result["error"] = f"{type(e).__name__}: {e}"
    result["detail"] = result["error"]
print(json.dumps(result))
"""


def verify_kernel(comfy_path: str) -> VerifyResponse:
    try:
        env = resolve_environment(comfy_path)
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        return VerifyResponse(ok=False, error=str(exc), detail=str(exc))

    if not env.python_path:
        return VerifyResponse(ok=False, error="No Python resolved", detail="No Python resolved")

    try:
        proc = subprocess.run(
            [env.python_path, "-c", KERNEL_SCRIPT],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return VerifyResponse(ok=False, error="Kernel test timed out", detail="Timed out")
    except OSError as exc:
        return VerifyResponse(ok=False, error=str(exc), detail=str(exc))

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        err = proc.stderr or proc.stdout or "No output from kernel test"
        return VerifyResponse(ok=False, error=err, detail=err)

    data = json.loads(lines[-1])
    return VerifyResponse(
        ok=bool(data.get("ok")),
        skipped=bool(data.get("skipped")),
        cosine=data.get("cosine"),
        dtype=data.get("dtype"),
        detail=data.get("detail") or "",
        error=data.get("error"),
    )


def launch_command(comfy_path: str) -> str:
    env = resolve_environment(comfy_path)
    main_py = env.main_py or str(Path(env.comfy_path) / "main.py")
    py = env.python_path or "python"
    return f'"{py}" "{main_py}" --use-sage-attention'
