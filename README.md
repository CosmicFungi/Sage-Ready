# Sage Ready

A local web app that makes **SageAttention** install correctly for **ComfyUI**—into the right Python—and proves it with a real GPU attention test so nodes won’t crash or spit out black/noisy frames.

**Version 1.2** is the release hardening pass: clearer guidance, safer Python selection, strict package-location checks, Ready only when the full checklist passes (including GPU), and fixes for install/repair edge cases.

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
3. If anything fails, click **Install & Fix**. Use **Repair** for wrong-folder installs or black/noisy output.
4. When you see **Step 3 · Ready**, **fully restart ComfyUI** with `--use-sage-attention` (or save the helper script).

## What “Ready” means

All of these must pass against **ComfyUI’s own Python** (not a random system Python):

| Check | Purpose |
|-------|---------|
| ComfyUI folder | `main.py` found |
| ComfyUI Python | prefers portable `python_embeded` or a local `.venv` |
| NVIDIA GPU | driver visible via `nvidia-smi` |
| PyTorch CUDA | `torch.cuda.is_available()` |
| Compatible package | SA 2.x prebuilt wheel (Windows) or pip plan (Linux) |
| Triton | importable (`triton-windows` on Windows) |
| SageAttention import | `from sageattention import sageattn` |
| Version | recommended wheel when a better match exists (e.g. post6) |
| Package location | under ComfyUI’s Python prefix |
| GPU attention test | HND + NHD layouts; similarity vs PyTorch ≥ 0.99 |

Known-bad builds such as **2.2.0.post5** (black/noise risk) are flagged; Repair upgrades toward **post6** when a matching wheel exists.

## Windows portable ComfyUI

Point at the portable root or the inner `ComfyUI` folder. The app prefers:

`python_embeded\python.exe`

(ComfyUI’s spelling of “embedded”.) Everything is installed with that interpreter’s `python -m pip`.

## Linux

Prebuilt Windows wheels don’t apply. The installer tries `sageattention==2.2.0 --no-build-isolation`, then falls back to `sageattention==1.0.6`. A CUDA toolkit / build chain may be required for SA 2.x.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| “No main.py” | Select the folder that contains `main.py` |
| Wrong Python / module not found in ComfyUI | Prefer portable `python_embeded` or a `.venv` beside ComfyUI, then **Repair** |
| No GPU / nvidia-smi missing | Install NVIDIA drivers |
| PyTorch has no CUDA | Install a CUDA PyTorch build into ComfyUI’s Python (not CPU torch) |
| No matching SA 2.x wheel | Upgrade Torch/CUDA, or accept the 1.0.6 fallback |
| Triton missing | **Install & Fix** |
| Black or noisy images | **Repair** to post6+; re-run **Test GPU** |
| GPU test skipped | Ready needs an NVIDIA GPU |
| SageAttention not used in ComfyUI | Restart with `--use-sage-attention` or the helper script |

## API

- `GET /api/health`
- `POST /api/resolve` `{ "comfy_path": "..." }`
- `POST /api/scan` `{ "comfy_path": "..." }`
- `POST /api/install` `{ "comfy_path": "...", "mode": "install"|"repair" }` (SSE log stream)
- `POST /api/verify` `{ "comfy_path": "..." }`
- `POST /api/launch-command` / `POST /api/write-helper`
- `GET /api/status`

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Does not install ComfyUI or model weights.
- Does not install Visual Studio Build Tools or compile CUDA extensions from source.
- Wheel downloads are allowlisted to official [woct0rdho/SageAttention releases](https://github.com/woct0rdho/SageAttention/releases).
- Prefer binding to `127.0.0.1` (default). Non-localhost binds can let other machines trigger installs.
- Wheel matrix: `sage_ready/wheels_matrix.json`.
