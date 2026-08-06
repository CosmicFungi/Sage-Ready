# Sage Ready — Install, Run & Guide

One file for everything: install Sage Ready, run it, and use it to make **SageAttention** safe for **ComfyUI**.

**Version:** 1.3.1  
**Mode:** local-only (will **not** start in Cursor Cloud / remote agents)

---

## 0. Local-only (important)

Sage Ready refuses to run in Cursor Cloud so it cannot “see” a fake `/workspace/B:\...` path.

- Starts only on your own PC
- Binds only to `http://127.0.0.1:8765`
- Scan/Install APIs return **403** on cloud/agent hosts

If `py app.py` prints `Refusing to start on a cloud/agent host`, you are not on your ComfyUI machine — download the ZIP onto that PC and run it there.

---

## 1. Install Sage Ready

### Requirements

- Python 3.10+ (3.11/3.12 recommended) **on the same PC as ComfyUI**
- An existing **ComfyUI** install (this app does not install ComfyUI)
- NVIDIA GPU + drivers for a full “Ready” result
- Internet access to download Triton / SageAttention wheels when you click Install & Fix

### Steps

```bash
# From this repo folder
cd /path/to/MyLab

python -m pip install -r requirements.txt
```

On Windows, `py` often works better:

```bat
py -m pip install -r requirements.txt
```

Optional: use a virtual environment for Sage Ready itself (separate from ComfyUI):

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Check import:

```bash
python -c "from sage_ready import __version__; print(__version__)"
```

You should see `1.3.1`.

---

## 2. Run Sage Ready

**Important:** Run Sage Ready on the **same computer** where ComfyUI is installed.

### How to know you’re on the local app

In the page header you should see something like:

`Local Windows · v1.3.1`

And the address bar must be:

`http://127.0.0.1:8765`

If you see `BLOCKED · cloud/agent` or a path error containing `/workspace/`, close that tab and use the local URL after `py app.py` on your ComfyUI PC.

### Download onto Windows (correct branch)

1. Open: https://github.com/CosmicFungi/MyLab/tree/cursor/sage-attention-comfyui-ecca  
2. **Code → Download ZIP**  
3. Extract to e.g. `C:\SageReady\`  
4. In that folder (must contain `app.py` and `GUIDE.md`), run:

```bat
py -m pip install -r requirements.txt
py app.py
```

5. Only use the browser tab that opens to `http://127.0.0.1:8765`
6. Paste your ComfyUI folder — **example:** `B:\ComfyUI_windows_portable\ComfyUI`

```bash
python app.py
```

- Opens `http://127.0.0.1:8765` in your browser
- Keep the terminal window open while you use the UI

### Useful options

```bash
# Don't auto-open the browser
python app.py --no-browser

# Custom port
python app.py --port 8765

# Both
python app.py --no-browser --port 8765
```

Then open the URL shown in the terminal (default `http://127.0.0.1:8765`).

Stay on `127.0.0.1` / `localhost`. Non-loopback binds are refused.

Stop the app with `Ctrl+C` in the terminal.

---

## 3. Guide — Use with ComfyUI

### What this app does

1. Finds your ComfyUI folder and the **correct Python** (`python_embeded`, `.venv`, etc.)
2. Scans GPU / PyTorch / Triton / SageAttention
3. Installs or repairs packages **into that ComfyUI Python**
4. Runs a real GPU attention test so nodes don’t crash or spit black/noisy frames
5. Gives you the exact launch command with `--use-sage-attention`

### Step-by-step in the UI

1. **Locate** — Paste the ComfyUI folder that contains `main.py`  
   - **Example:** `B:\ComfyUI_windows_portable\ComfyUI`  
   - Portable root **or** the inner `ComfyUI` folder both work  
   - Windows portable spelling is `python_embeded` (yes, that spelling)
2. Click **Scan**
3. Read the checklist  
   - Red / fail → click **Install & Fix**  
   - Wrong Python, black/noisy output, or old build → click **Repair**
4. Wait for the install log to finish; the app re-scans automatically
5. When you see **Step 3 · Ready**:
   - **Fully restart ComfyUI** (close it if it’s already open)
   - Start with the copy-paste command, **or** click **Save helper script** and run that

### Install & Fix vs Repair

| Button | Use when |
|--------|----------|
| **Install & Fix** | Packages are missing; first-time setup |
| **Repair** | Wrong folder/Python, black/noisy images, or upgrade to a safer wheel (e.g. post6) |
| **Test GPU** | Re-run the attention kernel check after a change |

Install & Fix will automatically switch to repair mode when it detects a bad/outdated/wrong-location install.

### After Ready — start ComfyUI

ComfyUI will **not** use SageAttention unless you pass the flag:

```bash
"<your-comfy-python>" "<your-ComfyUI>/main.py" --use-sage-attention
```

Or use the helper script written next to `main.py`:

- Windows: `run_sage_attention.bat`
- Linux: `run_sage_attention.sh`

Existing helpers are backed up to `*.bak` before overwrite.

---

## 4. Platform notes

### Windows portable ComfyUI

Point Sage Ready at the portable root or the inner `ComfyUI` folder.

**Example path:** `B:\ComfyUI_windows_portable\ComfyUI`

Preferred interpreter:

```text
python_embeded\python.exe
```

Everything is installed with:

```text
python_embeded\python.exe -m pip install …
```

### Linux

Windows prebuilt wheels don’t apply. Install & Fix tries:

1. `sageattention==2.2.0` (`--no-build-isolation`)
2. Fallback: `sageattention==1.0.6`

A CUDA toolkit / build chain may be required for SageAttention 2.x.

---

## 5. What “Ready” means

All of these must pass against **ComfyUI’s own Python** (not a random system Python):

| Check | Purpose |
|-------|---------|
| ComfyUI folder | `main.py` found |
| ComfyUI Python | prefers portable `python_embeded` or a local `.venv` |
| NVIDIA GPU | driver visible via `nvidia-smi` |
| PyTorch CUDA | `torch.cuda.is_available()` |
| Compatible package | SA 2.x wheel (Windows) or pip plan (Linux) |
| Triton | importable (`triton-windows` on Windows) |
| SageAttention import | `from sageattention import sageattn` |
| Version | recommended wheel when a better match exists (e.g. post6) |
| Package location | under ComfyUI’s Python prefix |
| GPU attention test | HND + NHD; similarity vs PyTorch ≥ 0.99 |

Known-bad builds such as **2.2.0.post5** (black/noise risk) are flagged; Repair upgrades toward **post6** when available.

Wheel tags like `2.2.0+cu130torch2.10.0andhigher.post6` count as **2.2.0.post6** (no false upgrade warning).

Fallback Python (system/conda instead of portable/venv) can install packages, but **blocks Ready** so you don’t get a false green light.

---

## 6. Troubleshooting

| Symptom | What to do |
|---------|------------|
| Path / “No main.py” | Select the folder that contains `main.py` (example: `B:\ComfyUI_windows_portable\ComfyUI`) |
| Wrong Python / module not found in ComfyUI | Prefer `python_embeded` or a `.venv` beside ComfyUI, then **Repair** |
| No GPU / `nvidia-smi` missing | Install NVIDIA drivers |
| PyTorch has no CUDA | Install a CUDA PyTorch build into ComfyUI’s Python (not CPU torch) |
| No matching SA 2.x wheel | Upgrade Torch/CUDA, or accept the 1.0.6 fallback |
| Triton missing | **Install & Fix** |
| Black or noisy images | **Repair** to post6+; re-run **Test GPU** |
| GPU test skipped | Ready needs an NVIDIA GPU |
| SageAttention not used in ComfyUI | Restart with `--use-sage-attention` or the helper script |
| Can’t open the UI | Confirm the terminal still shows Sage Ready running; try `http://127.0.0.1:8765` |
| `/workspace/` in errors | You’re on Cursor Cloud — run locally on your ComfyUI PC instead |

---

## 7. Tests (optional)

```bash
python -m unittest discover -s tests -v
```

---

## 8. Notes / limits

- Does **not** install ComfyUI or model weights
- Does **not** install Visual Studio Build Tools or compile CUDA from source
- Wheel downloads are allowlisted to official [woct0rdho/SageAttention releases](https://github.com/woct0rdho/SageAttention/releases)
- Wheel matrix: `sage_ready/wheels_matrix.json`
- Local-only: will not start under Cursor Cloud (`CURSOR_AGENT`)
