"""Shared SageAttention GPU kernel probe (run inside target ComfyUI Python)."""

from __future__ import annotations

# Executed via subprocess: python -c KERNEL_SCRIPT
KERNEL_SCRIPT = r"""
import json, sys
result = {
    "ok": False,
    "skipped": False,
    "cosine": None,
    "dtype": None,
    "layouts": [],
    "detail": "",
    "error": None,
}
try:
    import torch
    from sageattention import sageattn
    if not torch.cuda.is_available():
        result["skipped"] = True
        result["detail"] = (
            "No NVIDIA GPU available for the GPU attention test. "
            "Ready cannot complete without a GPU."
        )
        print(json.dumps(result))
        sys.exit(0)

    torch.manual_seed(0)
    device = "cuda"
    dtype = torch.float16
    B, H, S, D = 1, 4, 128, 64
    layouts_ok = []
    min_cosine = None

    def _cosine(a, b):
        aa = a.reshape(-1).float()
        bb = b.reshape(-1).float()
        return float(
            torch.nn.functional.cosine_similarity(
                aa.unsqueeze(0), bb.unsqueeze(0)
            ).item()
        )

    # HND: (batch, heads, seq, dim) — ComfyUI / sageattn default
    q = torch.randn(B, H, S, D, device=device, dtype=dtype)
    k = torch.randn(B, H, S, D, device=device, dtype=dtype)
    v = torch.randn(B, H, S, D, device=device, dtype=dtype)
    with torch.no_grad():
        out_sage = sageattn(q, k, v, tensor_layout="HND", is_causal=False)
        out_sdpa = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, is_causal=False
        )
    c_hnd = _cosine(out_sage, out_sdpa)
    layouts_ok.append({"layout": "HND", "cosine": c_hnd})
    min_cosine = c_hnd

    # NHD: (batch, seq, heads, dim)
    qn = q.transpose(1, 2).contiguous()
    kn = k.transpose(1, 2).contiguous()
    vn = v.transpose(1, 2).contiguous()
    with torch.no_grad():
        out_sage_n = sageattn(qn, kn, vn, tensor_layout="NHD", is_causal=False)
        # SDPA expects HND-style for this comparison path; compare in HND space
        out_sage_n_hnd = out_sage_n.transpose(1, 2).contiguous()
        c_nhd = _cosine(out_sage_n_hnd, out_sdpa)
    layouts_ok.append({"layout": "NHD", "cosine": c_nhd})
    min_cosine = min(min_cosine, c_nhd)

    result["layouts"] = layouts_ok
    result["cosine"] = float(min_cosine)
    result["dtype"] = "float16"
    result["ok"] = min_cosine >= 0.99
    if result["ok"]:
        result["detail"] = (
            f"GPU attention test passed (similarity {min_cosine:.5f} vs PyTorch; "
            f"need at least 0.99). Layouts: HND + NHD."
        )
    else:
        result["detail"] = (
            f"GPU attention test failed (similarity {min_cosine:.5f}; need 0.99). "
            "This wheel can cause black or noisy images in ComfyUI — "
            "click Repair, then Test GPU again."
        )
except Exception as e:
    result["error"] = f"{type(e).__name__}: {e}"
    result["detail"] = (
        f"GPU attention test error: {type(e).__name__}: {e}. "
        "Click Install & Fix (or Repair), then Test GPU again."
    )
print(json.dumps(result))
"""
