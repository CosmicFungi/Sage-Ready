"""GPU kernel verification for SageAttention."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .detect import resolve_environment
from .kernel import KERNEL_SCRIPT
from .models import VerifyResponse


def verify_kernel(comfy_path: str) -> VerifyResponse:
    try:
        env = resolve_environment(comfy_path)
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        return VerifyResponse(ok=False, error=str(exc), detail=str(exc))

    if not env.python_path:
        return VerifyResponse(
            ok=False,
            error="No Python found for this ComfyUI folder",
            detail="No Python found for this ComfyUI folder",
        )

    try:
        proc = subprocess.run(
            [env.python_path, "-c", KERNEL_SCRIPT],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return VerifyResponse(
            ok=False,
            error="GPU attention test timed out",
            detail="GPU attention test timed out",
        )
    except OSError as exc:
        return VerifyResponse(ok=False, error=str(exc), detail=str(exc))

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        err = proc.stderr or proc.stdout or "No output from GPU attention test"
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
