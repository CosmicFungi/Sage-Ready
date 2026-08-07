# Sage Ready — Install, Run & Guide (Linux v1.34)

Make **SageAttention** Ready for **ComfyUI** on Linux (Windows portable path still works when run on Windows).

**Author:** [CosmicFungi](https://github.com/CosmicFungi)  
**Version:** 1.34  
**License:** MIT  
**Mode:** local-only (will **not** start in Cursor Cloud / remote agents)  
**Branch:** [`cursor/sage-ready-linux-ecca`](https://github.com/CosmicFungi/MyLab/tree/cursor/sage-ready-linux-ecca)

---

## 0. Local-only (important)

Sage Ready refuses to run in Cursor Cloud so it cannot “see” a fake `/workspace/B:\...` path.

- Starts only on your own PC
- Binds only to `http://127.0.0.1:8765`
- Scan/Install APIs return **403** on cloud/agent hosts
- Public `/api/health` never includes your PC hostname or cwd

If `python app.py` prints `Refusing to start on a cloud/agent host`, download the ZIP onto your ComfyUI machine and run it there.

---

## 1. Install Sage Ready

### Requirements

- Python 3.10+ on the **same PC as ComfyUI**
- Existing ComfyUI install
- NVIDIA GPU + drivers for a full Ready result
- Internet for Triton / SageAttention downloads
- Linux SA 2.x builds often need a CUDA toolkit / `nvcc`

### Linux

```bash
cd /path/to/Sage-Ready
python -m pip install -r requirements.txt
python -c "from sage_ready import __version__; print(__version__)"
```

You should see `1.34`.

### Windows

```bat
py -m pip install -r requirements.txt
```

---

## 2. Run

```bash
python app.py
```

Open **only** `http://127.0.0.1:8765`. Header should show:

`Local Linux · v1.34`

### Download

1. https://github.com/CosmicFungi/MyLab/tree/cursor/sage-ready-linux-ecca  
2. **Code → Download ZIP**  
3. Extract and run from the folder that contains `app.py`

---

## 3. Use the UI

1. Paste ComfyUI folder (contains `main.py`)
   - Linux: `/home/you/ComfyUI`
   - Windows: `B:\ComfyUI_windows_portable\ComfyUI`
2. Prefer ComfyUI’s own Python (`.venv` on Linux; `python_embeded` on Windows portable)
3. **Scan** → **Install & Fix** (or **Repair**)
4. When Ready, restart ComfyUI with `--use-sage-attention`

System/conda fallback Python can install packages but **blocks Ready**.

The launch-flag checklist item stays **WARN** until you actually start ComfyUI with that flag — that is expected, not a broken install.

---

## 4. Linux install details

1. `triton` (torch ≥ 2.10 → `>=3.6,<4`)
2. `sageattention==2.2.0` with `--no-build-isolation`
3. Fallback `sageattention==1.0.6` if the build fails

**Not auto-installed:** community Hugging Face / third-party Linux wheels.

### CUDA 13.x / PyTorch 2.14

| Topic | Behavior |
|-------|----------|
| `cu132` | Maps to **130** in planning notes |
| `cu129` | Maps to **128** |
| PyTorch 2.14+ | Scan/plan aware; Windows wheel matrix max **2.13**; Linux uses pip/build |

---

## 5. What Ready means

| Check | Purpose |
|-------|---------|
| ComfyUI folder | `main.py` found |
| ComfyUI Python | local `.venv` / portable `python_embeded` (not fallback) |
| NVIDIA GPU | `nvidia-smi` |
| PyTorch CUDA | `torch.cuda.is_available()` |
| Package plan | Windows wheel or Linux pip plan |
| Triton | importable |
| SageAttention import | `from sageattention import sageattn` |
| Version | matches planned target when applicable |
| Package location | under ComfyUI’s Python prefix |
| GPU attention test | HND + NHD vs SDPA ≥ 0.99 |

---

## 6. Troubleshooting

| Symptom | What to do |
|---------|------------|
| Windows path on Linux | Use `/home/…/ComfyUI` |
| Wrong Python | Create `.venv` beside ComfyUI, then Repair |
| SA 2.2.0 build failed | Install CUDA toolkit/`nvcc`, or accept 1.0.6 |
| False “upgrade” on Windows post6 | Wheel local tags like `…post6` count as `2.2.0.post6` |
| Launch flag WARN | Expected until you start ComfyUI with `--use-sage-attention` |
| `/workspace/` errors | You’re on Cursor Cloud — run locally |
| Hostname in UI | Should never appear (health API omits it) |

---

## 7. Tests

```bash
python -m unittest discover -s tests -v
# or
python -m pytest tests/ -q
```

Release regressions live in `tests/test_linux_release.py` and `tests/test_release_bugs.py`.

---

## 8. Limits

- Does not install ComfyUI or models
- Does not auto-download untrusted Linux wheels
- Windows wheels allowlisted to [woct0rdho/SageAttention releases](https://github.com/woct0rdho/SageAttention/releases)
- Matrix / Linux strategy: `sage_ready/wheels_matrix.json`

---

## 9. Credits & license

**[CosmicFungi](https://github.com/CosmicFungi)** — MIT License.

SageAttention by [thu-ml](https://github.com/thu-ml/SageAttention). ComfyUI by [comfyanonymous](https://github.com/comfyanonymous/ComfyUI).
