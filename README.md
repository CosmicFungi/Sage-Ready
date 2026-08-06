# Sage Ready (local-only)

Makes **SageAttention** install correctly for **ComfyUI** on **this PC**.

**Will not start in Cursor Cloud / remote Linux agents.**  
Run it on the machine where ComfyUI lives.

**Full guide:** [GUIDE.md](GUIDE.md)

## Quick start (Windows)

1. Download ZIP:  
   https://github.com/CosmicFungi/MyLab/tree/cursor/sage-attention-comfyui-ecca  
   → **Code → Download ZIP**
2. Extract → open a terminal in the folder that contains `app.py`
3. Run:

```bat
py -m pip install -r requirements.txt
py app.py
```

4. Open **only** `http://127.0.0.1:8765`  
   Header should say `Local Windows · …`
5. Paste your ComfyUI folder (the one with `main.py`), for example:  
   `B:\ComfyUI_windows_portable\ComfyUI`
6. **Scan** → **Install & Fix** → when Ready, restart ComfyUI with `--use-sage-attention`

## Linux / macOS

```bash
pip install -r requirements.txt
python app.py
```

Use a local ComfyUI path such as `/home/you/ComfyUI`. Windows drive letters (`B:\…`) only work when Sage Ready runs on Windows.
