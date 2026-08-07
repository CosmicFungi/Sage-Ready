"""Pydantic models for the Sage Ready API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .paths import ComfyPathMixin


class CheckStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class PathRequest(ComfyPathMixin, BaseModel):
    comfy_path: str = Field(..., min_length=1)


class InstallRequest(ComfyPathMixin, BaseModel):
    comfy_path: str = Field(..., min_length=1)
    mode: str = Field(default="install", pattern="^(install|repair)$")
    dry_run: bool = False


class CheckItem(BaseModel):
    id: str
    title: str
    status: CheckStatus
    detail: str = ""
    fix_hint: str = ""


class EnvSnapshot(BaseModel):
    comfy_path: str
    main_py: Optional[str] = None
    python_path: Optional[str] = None
    python_prefix: Optional[str] = None
    environment_type: str = "unknown"
    python_is_fallback: bool = False
    python_version: str = ""
    platform: str = ""
    torch_version: Optional[str] = None
    torch_cuda: Optional[str] = None
    torch_cuda_available: bool = False
    gpu_name: Optional[str] = None
    driver_version: Optional[str] = None
    triton_version: Optional[str] = None
    sageattention_version: Optional[str] = None
    sageattention_location: Optional[str] = None
    site_packages: list[str] = Field(default_factory=list)
    pip_ok: bool = False
    has_use_sage_flag: bool = False
    launch_scripts: list[str] = Field(default_factory=list)
    needs_repair: bool = False


class WheelPlan(BaseModel):
    strategy: str
    sage_version: str
    package_spec: str
    triton_package: str
    triton_constraint: str
    wheel_url: Optional[str] = None
    notes: str = ""


class ResolveResponse(BaseModel):
    ok: bool
    env: Optional[EnvSnapshot] = None
    wheel_plan: Optional[WheelPlan] = None
    error: Optional[str] = None


class ScanResponse(BaseModel):
    ok: bool
    env: Optional[EnvSnapshot] = None
    wheel_plan: Optional[WheelPlan] = None
    checks: list[CheckItem] = Field(default_factory=list)
    ready_for_install: bool = False
    ready: bool = False
    summary: str = ""
    error: Optional[str] = None


class VerifyResponse(BaseModel):
    ok: bool
    skipped: bool = False
    cosine: Optional[float] = None
    dtype: Optional[str] = None
    detail: str = ""
    error: Optional[str] = None


class StatusResponse(BaseModel):
    version: str
    last_scan: Optional[ScanResponse] = None
    last_verify: Optional[VerifyResponse] = None
    last_install: Optional[dict[str, Any]] = None
