# Sage Ready — Linux

**Make SageAttention Ready for ComfyUI**

Local-only installer and readiness checker for [SageAttention](https://github.com/thu-ml/SageAttention) inside an existing **ComfyUI** install.

**Line:** Linux v1.34 (from Windows v1.33)  
**Author:** [CosmicFungi](https://github.com/CosmicFungi)  
**License:** [MIT](LICENSE)  
**Branch:** [`cursor/sage-ready-linux-ecca`](https://github.com/CosmicFungi/MyLab/tree/cursor/sage-ready-linux-ecca)

Will **not** start in Cursor Cloud / remote agents. Run it on the PC where ComfyUI lives.

**Full guide:** [GUIDE.md](GUIDE.md)

---

## Quick start (Linux)

1. Download ZIP:  
   https://github.com/CosmicFungi/MyLab/tree/cursor/sage-ready-linux-ecca  
   → **Code → Download ZIP**
2. Extract → open a terminal in the folder that contains `app.py`
3. Run:

```bash
pip install -r requirements.txt
python app.py
```

4. Open **only** `http://127.0.0.1:8765`  
   Header should say `Local Linux · v1.34`
5. Paste your ComfyUI folder (contains `main.py`), for example:  
   `/home/you/ComfyUI`
6. Prefer a **`.venv`** beside ComfyUI
7. **Scan** → **Install & Fix** → when Ready, restart ComfyUI with `--use-sage-attention`

### Install & Fix on Linux

1. Installs **`triton`** (constrained to your PyTorch; torch ≥ 2.10 → `>=3.6,<4`)
2. Tries **`sageattention==2.2.0`** (`--no-build-isolation`; may need CUDA toolkit / `nvcc`)
3. Falls back to **`sageattention==1.0.6`** if the 2.x build fails

Community Hugging Face Linux wheels are **not** auto-installed.

### CUDA 13.x / PyTorch 2.14

| Topic | Behavior |
|-------|----------|
| `cu132` | Detected; planning notes map to the **130** line |
| `cu129` | Maps to **128** |
| PyTorch 2.14+ | Supported for scan/plan; curated Windows wheels max at **2.13**; Linux uses pip/build |

## Windows (same codebase)

```bat
py -m pip install -r requirements.txt
py app.py
```

Use e.g. `B:\ComfyUI_windows_portable\ComfyUI`. Matching **woct0rdho** prebuilt wheels are used when available.

---

## Repository layout

| Path | Description |
|------|-------------|
| `app.py` | Entry point — local FastAPI on `127.0.0.1:8765` |
| `requirements.txt` | Sage Ready dependencies (not ComfyUI) |
| `GUIDE.md` | Full install / run / usage guide |
| `LICENSE` | MIT — Copyright CosmicFungi |
| `README.md` | Overview and project map |
| `publish-to-sage-ready.sh` | Optional publish helper for CosmicFungi/Sage-Ready |
| `web/` | Browser UI (`index.html`, `styles.css`, `app.js`) |
| `sage_ready/` | Detect, install, verify, wheels matrix, local-only guard |
| `sage_ready/wheels_matrix.json` | Windows wheels + Linux strategy metadata |
| `tests/` | Unit + release regression tests |

---

## Credits

Created and maintained by **[CosmicFungi](https://github.com/CosmicFungi)**.

SageAttention is by [thu-ml](https://github.com/thu-ml/SageAttention). ComfyUI is by [comfyanonymous](https://github.com/comfyanonymous/ComfyUI).
