"""Final release regressions — Windows-era bugs + Linux v1.34 release gates."""

from __future__ import annotations

import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app import app
from sage_ready import __version__
from sage_ready.checks import build_checks, summarize
from sage_ready.detect import resolve_python
from sage_ready.local_guard import runtime_info
from sage_ready.models import CheckItem, CheckStatus, EnvSnapshot
from sage_ready.paths import validate_comfy_path_for_host
from sage_ready.versioning import normalize_sage_version, versions_equivalent
from sage_ready.wheels import needs_version_upgrade, plan_install


class PriorReleaseBugRegressions(unittest.TestCase):
    """Bugs fixed on the Windows v1.33 line must stay fixed on Linux v1.34."""

    def test_version_is_134(self):
        self.assertEqual(__version__, "1.34")

    def test_health_never_leaks_hostname_or_cwd(self):
        # LeonPC-style hostnames must never appear in the public API
        info = runtime_info()
        self.assertNotIn("hostname", info)
        self.assertNotIn("cwd", info)
        client = TestClient(app)
        data = client.get("/api/health").json()
        self.assertNotIn("hostname", data)
        self.assertNotIn("cwd", data)
        self.assertEqual(data["version"], "1.34")
        self.assertTrue(data.get("local_only"))

    def test_cloud_scan_still_forbidden(self):
        client = TestClient(app)
        r = client.post("/api/scan", json={"comfy_path": "/home/you/ComfyUI"})
        self.assertEqual(r.status_code, 403)
        body = r.json()
        self.assertTrue(body.get("local_only") or "local" in str(body).lower())

    def test_windows_drive_path_rejected_on_linux(self):
        if platform.system().lower().startswith("win"):
            self.skipTest("Host is Windows")
        with self.assertRaises(ValueError) as ctx:
            validate_comfy_path_for_host(r"B:\ComfyUI_windows_portable\ComfyUI")
        self.assertIn("Windows", str(ctx.exception))

        # Easy-Install style path also rejected (not a valid Linux path)
        with self.assertRaises(ValueError):
            validate_comfy_path_for_host(
                r"B:\ComfyUI-Easy-Install-Windows\ComfyUI-Easy-Install\ComfyUI"
            )

    def test_post6_wheel_local_tag_not_false_upgrade(self):
        # Classic Windows false WARN: installed post6 local tag vs plan post6
        wheel_ver = "2.2.0+cu130torch2.10.0andhigher.post6"
        self.assertEqual(normalize_sage_version(wheel_ver), "2.2.0.post6")
        self.assertTrue(versions_equivalent(wheel_ver, "2.2.0.post6"))
        env = EnvSnapshot(
            comfy_path="/c",
            python_version="3.12.0",
            torch_version="2.12.0+cu130",
            torch_cuda="13.0",
            torch_cuda_available=True,
            sageattention_version=wheel_ver,
        )
        plan = plan_install(env, host_platform="windows")
        self.assertEqual(plan.strategy, "wheel")
        self.assertFalse(needs_version_upgrade(env, plan))

    def test_launch_flag_warn_does_not_block_must_ok_list(self):
        # Launch flag WARN is expected until ComfyUI is started with --use-sage-attention
        checks = [
            CheckItem(id="comfy_root", title="root", status=CheckStatus.OK),
            CheckItem(id="python", title="py", status=CheckStatus.OK),
            CheckItem(id="nvidia_gpu", title="gpu", status=CheckStatus.OK),
            CheckItem(id="torch", title="torch", status=CheckStatus.OK),
            CheckItem(id="triton", title="triton", status=CheckStatus.OK),
            CheckItem(id="sageattention", title="sa", status=CheckStatus.OK),
            CheckItem(id="package_location", title="loc", status=CheckStatus.OK),
            CheckItem(id="kernel_test", title="kernel", status=CheckStatus.OK),
            CheckItem(id="launch_flag", title="flag", status=CheckStatus.WARN),
        ]
        env = EnvSnapshot(comfy_path="/c", python_is_fallback=False)
        ready_for_install, ready, summary = summarize(checks, env)
        self.assertTrue(ready_for_install)
        self.assertTrue(ready)
        self.assertIn("ready", summary.lower())


class LinuxReleaseGates(unittest.TestCase):
    def test_linux_plan_matches_pip_target(self):
        env = EnvSnapshot(
            comfy_path="/home/you/ComfyUI",
            python_version="3.12.0",
            torch_version="2.14.0+cu132",
            torch_cuda="13.2",
            torch_cuda_available=True,
        )
        plan = plan_install(env, host_platform="linux")
        self.assertEqual(plan.strategy, "pip_sa2_or_fallback")
        self.assertEqual(plan.sage_version, "2.2.0")
        self.assertEqual(plan.package_spec, "sageattention==2.2.0")
        self.assertIsNone(plan.wheel_url)
        self.assertIn("2.14", plan.notes)
        self.assertIn("132", plan.notes)

    def test_linux_sa2_checklist_green(self):
        env = EnvSnapshot(
            comfy_path="/home/you/ComfyUI",
            python_path="/home/you/ComfyUI/.venv/bin/python",
            python_version="3.12.0",
            platform="linux",
            torch_version="2.14.0+cu132",
            torch_cuda="13.2",
            torch_cuda_available=True,
            sageattention_version="2.2.0",
            sageattention_location="/home/you/ComfyUI/.venv/lib/python3.12/site-packages/sageattention",
            python_prefix="/home/you/ComfyUI/.venv",
            site_packages=["/home/you/ComfyUI/.venv/lib/python3.12/site-packages"],
            triton_version="3.6.0",
            gpu_name="NVIDIA",
            driver_version="560",
        )
        plan = plan_install(env, host_platform="linux")
        checks = build_checks(
            env,
            plan,
            probe={
                "sageattn_import_ok": True,
                "sageattention_location": env.sageattention_location,
            },
        )
        by_id = {c.id: c for c in checks}
        self.assertEqual(by_id["wheel_match"].status, CheckStatus.OK)
        self.assertEqual(by_id["sa_version"].status, CheckStatus.OK)
        self.assertFalse(needs_version_upgrade(env, plan))

    def test_linux_ignores_home_venv(self):
        if platform.system().lower().startswith("win"):
            self.skipTest("Linux discovery")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rogue = home / ".venv" / "bin"
            rogue.mkdir(parents=True)
            rogue_py = rogue / "python"
            rogue_py.write_text("#!/bin/sh\n", encoding="utf-8")
            rogue_py.chmod(0o755)
            comfy = home / "ComfyUI"
            comfy.mkdir()
            main = comfy / "main.py"
            main.write_text("#\n", encoding="utf-8")
            with patch("sage_ready.detect._has_torch", return_value=True):
                env_type, path, fallback = resolve_python(comfy, main)
            self.assertTrue(fallback)
            self.assertNotEqual(path, rogue_py.resolve())

    def test_docs_and_ui_are_linux_release(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        guide = (ROOT / "GUIDE.md").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("1.34", readme)
        self.assertIn("1.34", guide)
        self.assertIn("1.34", html)
        self.assertIn("CosmicFungi", readme)
        self.assertIn("CosmicFungi", guide)
        self.assertIn("Make SageAttention Ready for ComfyUI", html)
        self.assertNotIn("Make SageAttention safe for ComfyUI", html)
        self.assertIn("/home/you/ComfyUI", readme)
        self.assertIn("cursor/sage-ready-linux-ecca", readme)
        self.assertTrue((ROOT / "LICENSE").is_file())
        license_txt = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("CosmicFungi", license_txt)
        self.assertIn("MIT License", license_txt)


if __name__ == "__main__":
    unittest.main()
