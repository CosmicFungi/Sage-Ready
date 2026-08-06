# Sage Ready

A local web app that makes **SageAttention** install correctly for **ComfyUI**—into the right Python—and proves it with a real GPU kernel test so nodes won’t crash or spit out black/noise frames.

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Opens `http://127.0.0.1:8765`.

```bash
python app.py --no-browser --port 8765
```

## How to use

1. Paste your **ComfyUI folder** (the one with `main.py`).
2. Click **Scan**.
3. If anything fails, click **Install & Fix** (or **Repair** to force-reinstall).
4. When you see **Ready**, start ComfyUI with `--use-sage-attention`.

The app writes a helper script (`run_sage_attention.bat` / `.sh`) into your ComfyUI folder.

## What “Ready” means

All of these must pass against **ComfyUI’s own Python** (not a random system Python):

| Check | Purpose |
|-------|---------|
| ComfyUI folder | `main.py` found |
| ComfyUI Python | portable `python_embeded`, `.venv`, conda, or system |
| NVIDIA GPU | driver visible via `nvidia-smi` |
| PyTorch CUDA | `torch.cuda.is_available()` |
| Wheel match | SA 2.x prebuilt wheel (Windows) or pip plan (Linux) |
| Triton | importable (`triton-windows` on Windows) |
| SageAttention import | `from sageattention import sageattn` |
| Package location | installed under the ComfyUI env |
| Kernel smoke test | `sageattn` vs SDPA cosine ≥ 0.99 |

Known-bad builds such as **2.2.0.post5** (black/noise risk) are flagged; Repair upgrades toward **post6** when a matching wheel exists.

## Windows portable ComfyUI

Point at the portable root or the inner `ComfyUI` folder. The app prefers:

`python_embeded\python.exe`

Everything is installed with:

```text
python_embeded\python.exe -m pip install …
```

## Linux

Prebuilt Windows wheels don’t apply. The installer tries `sageattention==2.2.0 --no-build-isolation`, then falls back to `sageattention==1.0.6`. A CUDA toolkit / build chain may be required for SA 2.x.

## Troubleshooting

| Checklist id | Common fix |
|--------------|------------|
| `comfy_root` | Select the folder that contains `main.py` |
| `python` | Use portable ComfyUI or create a `.venv` next to it |
| `nvidia_gpu` | Update NVIDIA drivers; confirm `nvidia-smi` works |
| `torch` | Install a CUDA PyTorch build into ComfyUI’s Python |
| `wheel_match` | Upgrade Torch/CUDA, or accept SA 1.0.6 fallback |
| `triton` | Click **Install & Fix** |
| `sageattention` | Click **Install & Fix** (wrong-env installs are the usual cause) |
| `package_location` | Use **Repair** so the wheel lands in ComfyUI’s site-packages |
| `kernel_test` | Repair to post6+; confirm GPU isn’t blocked |
| `launch_flag` | Use the copy-paste launch command or helper script |

## API

- `GET /api/health`
- `POST /api/resolve` `{ "comfy_path": "..." }`
- `POST /api/scan` `{ "comfy_path": "..." }`
- `POST /api/install` `{ "comfy_path": "...", "mode": "install"|"repair" }` (SSE log stream)
- `POST /api/verify` `{ "comfy_path": "..." }`
- `GET /api/status`

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Does not install ComfyUI or model weights.
- Does not install Visual Studio Build Tools or compile CUDA extensions from source.
- Wheel URLs come from [woct0rdho/SageAttention releases](https://github.com/woct0rdho/SageAttention/releases); the matrix lives in `sage_ready/wheels_matrix.json`.
