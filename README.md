# Sage Ready

**Make SageAttention Ready for ComfyUI**

Local-only installer and readiness checker for [SageAttention](https://github.com/thu-ml/SageAttention) inside an existing **ComfyUI** install.

**Author:** [CosmicFungi](https://github.com/CosmicFungi)  
**Version:** 1.33  
**License:** [MIT](LICENSE)

Will **not** start in Cursor Cloud / remote Linux agents. Run it on the PC where ComfyUI lives.

**Full guide:** [GUIDE.md](GUIDE.md)

---

## Quick start (Windows)

1. Download ZIP from this repo → **Code → Download ZIP**
2. Extract → open a terminal in the folder that contains `app.py`
3. Run:

```bat
py -m pip install -r requirements.txt
py app.py
```

4. Open **only** `http://127.0.0.1:8765`  
   Header should say `Local Windows · v1.33`
5. Paste your ComfyUI folder (the one with `main.py`), for example:  
   `B:\ComfyUI_windows_portable\ComfyUI`
6. **Scan** → **Install & Fix** → when Ready, restart ComfyUI with `--use-sage-attention`

## Linux / macOS

```bash
pip install -r requirements.txt
python app.py
```

Use a local ComfyUI path such as `/home/you/ComfyUI`. Windows drive letters (`B:\…`) only work when Sage Ready runs on Windows.

---

## Repository layout

| Path | Description |
|------|-------------|
| `app.py` | Main entry point. Starts the local FastAPI server on `127.0.0.1:8765` and serves the UI. |
| `requirements.txt` | Python dependencies for Sage Ready itself (not ComfyUI). |
| `GUIDE.md` | Full install, run, and usage guide. |
| `LICENSE` | MIT License. |
| `README.md` | This file — overview and project map. |
| `web/` | Browser UI served by the local app. |
| `web/index.html` | Page structure and copy. |
| `web/styles.css` | Layout and visual styling. |
| `web/app.js` | Client logic: scan, install stream, checklist, host badge. |
| `sage_ready/` | Core Python package (detect, install, verify). |
| `sage_ready/__init__.py` | Package version (`1.33`). |
| `sage_ready/paths.py` | ComfyUI path normalization and validation. |
| `sage_ready/detect.py` | Finds ComfyUI root and its Python (`python_embeded`, venv, etc.). |
| `sage_ready/checks.py` | Readiness checklist (GPU, CUDA torch, Triton, SageAttention, kernels). |
| `sage_ready/install.py` | Installs / repairs Triton and SageAttention into ComfyUI’s Python. |
| `sage_ready/verify.py` | GPU kernel verification and launch-command helpers. |
| `sage_ready/kernel.py` | Probe script run inside ComfyUI’s Python for HND/NHD kernels. |
| `sage_ready/wheels.py` | Matches Triton / SageAttention wheels to torch + CUDA + platform. |
| `sage_ready/wheels_matrix.json` | Known-good wheel URL matrix (Windows-focused). |
| `sage_ready/versioning.py` | Normalizes wheel local versions (e.g. `post6` tags). |
| `sage_ready/local_guard.py` | Blocks Cursor Cloud / non-localhost use. |
| `sage_ready/models.py` | API request/response models. |
| `tests/` | Unit tests for wheels, versioning, and release regressions. |
| `tests/test_wheels.py` | Wheel matrix and matching tests. |
| `tests/test_release_bugs.py` | API, path, and release regression tests. |

---

## Credits

Created and maintained by **[CosmicFungi](https://github.com/CosmicFungi)**.

SageAttention is by the [thu-ml](https://github.com/thu-ml/SageAttention) project. ComfyUI is by [comfyanonymous](https://github.com/comfyanonymous/ComfyUI). This tool only helps install and verify SageAttention for local ComfyUI use.
