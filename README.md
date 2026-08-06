# Sage Ready (local-only)

Makes **SageAttention** install correctly for **ComfyUI** on **this PC**.

**Will not start in Cursor Cloud / remote Linux agents.**  
Run it on the Windows machine where ComfyUI lives.

**Full guide:** [GUIDE.md](GUIDE.md)

## Windows (ComfyUI on `B:\` / `C:\`)

1. Download branch ZIP:  
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

5. Paste your ComfyUI folder, e.g.  
   `B:\ComfyUI-Easy-Install-Windows\ComfyUI-Easy-Install\ComfyUI`
