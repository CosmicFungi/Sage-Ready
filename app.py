#!/usr/bin/env python3
"""Sage Ready — local web app for ComfyUI SageAttention readiness."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sage_ready import __version__
from sage_ready.checks import scan_environment
from sage_ready.detect import resolve_environment
from sage_ready.install import install_stack, write_launch_helper
from sage_ready.models import (
    InstallRequest,
    PathRequest,
    ResolveResponse,
    ScanResponse,
    StatusResponse,
    VerifyResponse,
)
from sage_ready.verify import launch_command, verify_kernel
from sage_ready.wheels import plan_install

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="Sage Ready", version=__version__)

_state: dict[str, Any] = {
    "last_scan": None,
    "last_verify": None,
    "last_install": None,
}
_state_lock = threading.Lock()


def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        _state.update(kwargs)


@app.get("/api/health")
def health() -> dict[str, Any]:
    import platform as _platform
    import socket

    system = _platform.system()
    return {
        "status": "ok",
        "version": __version__,
        "platform": system,
        "platform_release": _platform.release(),
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "is_windows": system.lower().startswith("win"),
        "local_url_hint": "http://127.0.0.1:8765",
    }


@app.get("/api/status", response_model=StatusResponse)
def status() -> StatusResponse:
    with _state_lock:
        return StatusResponse(
            version=__version__,
            last_scan=_state["last_scan"],
            last_verify=_state["last_verify"],
            last_install=_state["last_install"],
        )


@app.post("/api/resolve", response_model=ResolveResponse)
def resolve(req: PathRequest) -> ResolveResponse:
    try:
        env = resolve_environment(req.comfy_path)
        plan = plan_install(env)
        return ResolveResponse(ok=True, env=env, wheel_plan=plan)
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        return ResolveResponse(ok=False, error=str(exc))


@app.post("/api/scan", response_model=ScanResponse)
def scan(req: PathRequest) -> ScanResponse:
    result = scan_environment(req.comfy_path, include_kernel=True)
    _set_state(last_scan=result)
    return result


@app.post("/api/verify", response_model=VerifyResponse)
def verify(req: PathRequest) -> VerifyResponse:
    result = verify_kernel(req.comfy_path)
    _set_state(last_verify=result)
    return result


@app.post("/api/launch-command")
def api_launch_command(req: PathRequest) -> dict[str, Any]:
    try:
        cmd = launch_command(req.comfy_path)
        return {"ok": True, "command": cmd, "helper_script": None}
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/write-helper")
def api_write_helper(req: PathRequest) -> dict[str, Any]:
    try:
        helper = write_launch_helper(req.comfy_path)
        cmd = launch_command(req.comfy_path)
        return {"ok": True, "command": cmd, "helper_script": helper}
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/install")
async def install(req: InstallRequest) -> StreamingResponse:
    queue: Queue[Optional[str]] = Queue()

    def worker() -> None:
        def log(msg: str) -> None:
            queue.put(json.dumps({"type": "log", "line": msg}))

        try:
            result = install_stack(
                req.comfy_path,
                mode=req.mode,
                dry_run=req.dry_run,
                log=log,
            )
            _set_state(last_install=result)
            queue.put(json.dumps({"type": "result", "ok": True, "result": result}))
        except Exception as exc:  # noqa: BLE001 — surface to UI
            _set_state(last_install={"ok": False, "error": str(exc)})
            queue.put(json.dumps({"type": "result", "ok": False, "error": str(exc)}))
        finally:
            queue.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_stream():
        # Keepalive-friendly headers applied on response
        while True:
            try:
                item = await asyncio.to_thread(queue.get, True, 0.5)
            except Empty:
                if not thread.is_alive():
                    while True:
                        try:
                            item = queue.get_nowait()
                        except Empty:
                            return
                        if item is None:
                            return
                        yield f"data: {item}\n\n"
                else:
                    yield ": keepalive\n\n"
                continue
            if item is None:
                break
            yield f"data: {item}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sage Ready for ComfyUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "WARNING: Binding outside localhost lets other machines trigger installs "
            "on this PC. Prefer --host 127.0.0.1 unless you trust the network."
        )

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    print(f"Sage Ready v{__version__}")
    print(f"Open {url}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
