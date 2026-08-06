# Sage Ready

Makes **SageAttention** install correctly for **ComfyUI** and proves it with a GPU attention test.

**Full install, run, and usage guide (one file):** [GUIDE.md](GUIDE.md)

## Windows users (ComfyUI on `B:\` / `C:\`)

1. Download this branch ZIP:  
   https://github.com/CosmicFungi/MyLab/tree/cursor/sage-attention-comfyui-ecca  
   → **Code → Download ZIP** (not the empty `main` branch)
2. Extract → open a terminal in the folder that contains `app.py`
3. Run:

```bat
py -m pip install -r requirements.txt
py app.py
```

4. Use **only** `http://127.0.0.1:8765`  
   The header must say `Running on Windows`. If you see `/workspace/` in an error, you’re still on the cloud page — close it.

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Opens `http://127.0.0.1:8765`. Details and troubleshooting: [GUIDE.md](GUIDE.md).
