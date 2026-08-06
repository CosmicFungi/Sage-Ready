"""Regression tests for release-blocking bugs found in QA."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app import app
from sage_ready.checks import (
    _parse_json_line,
    package_in_target_env,
    summarize,
)
from sage_ready.detect import find_launch_scripts, run_probe
from sage_ready.install import (
    _install_lock,
    _should_force_repair,
    install_stack,
    write_launch_helper,
)
from sage_ready.models import CheckItem, CheckStatus, EnvSnapshot, InstallRequest, PathRequest
from sage_ready.paths import path_under_prefix, strip_comfy_path
from sage_ready.versioning import parse_version_tuple
from sage_ready.wheels import (
    find_matching_wheel,
    is_known_bad_version,
    plan_install,
)
from sage_ready.verify import verify_kernel


class PathValidationTests(unittest.TestCase):
    def test_strip_whitespace(self):
        self.assertEqual(strip_comfy_path("  /tmp/ComfyUI  "), "/tmp/ComfyUI")
        with self.assertRaises(ValueError):
            strip_comfy_path("   ")

    def test_path_request_rejects_blank(self):
        with self.assertRaises(Exception):
            PathRequest(comfy_path="   ")

    def test_path_under_prefix_boundary(self):
        self.assertTrue(
            path_under_prefix(
                "/ComfyUI/python_embeded/Lib/site-packages/x.py",
                "/ComfyUI/python_embeded",
            )
        )
        self.assertFalse(
            path_under_prefix(
                "/ComfyUI/python_embeded_backup/Lib/site-packages/x.py",
                "/ComfyUI/python_embeded",
            )
        )


class PackageLocationTests(unittest.TestCase):
    def test_rejects_sibling_and_custom_nodes(self):
        env = EnvSnapshot(
            comfy_path="/ComfyUI",
            python_path="/ComfyUI/python_embeded/python.exe",
            python_prefix="/ComfyUI/python_embeded",
            site_packages=["/ComfyUI/python_embeded/Lib/site-packages"],
        )
        self.assertTrue(
            package_in_target_env(
                "/ComfyUI/python_embeded/Lib/site-packages/sageattention/__init__.py",
                env,
            )
        )
        self.assertFalse(
            package_in_target_env(
                "/ComfyUI/custom_nodes/foo/sageattention/__init__.py", env
            )
        )
        self.assertFalse(
            package_in_target_env(
                "/ComfyUI/.venv/lib/site-packages/sageattention/__init__.py", env
            )
        )


class ReadyGatingTests(unittest.TestCase):
    def _checks(self, **overrides):
        items = {
            "comfy_root": CheckStatus.OK,
            "python": CheckStatus.OK,
            "nvidia_gpu": CheckStatus.OK,
            "torch": CheckStatus.OK,
            "triton": CheckStatus.OK,
            "sageattention": CheckStatus.OK,
            "sa_version": CheckStatus.OK,
            "package_location": CheckStatus.OK,
            "kernel_test": CheckStatus.OK,
            "launch_flag": CheckStatus.WARN,
        }
        items.update(overrides)
        return [CheckItem(id=k, title=k, status=v) for k, v in items.items()]

    def test_nvidia_fail_blocks_ready(self):
        _, ready, _ = summarize(
            self._checks(nvidia_gpu=CheckStatus.FAIL),
            EnvSnapshot(comfy_path="/c"),
        )
        self.assertFalse(ready)

    def test_blocking_skip_summary(self):
        _, ready, summary = summarize(
            self._checks(kernel_test=CheckStatus.SKIP),
            EnvSnapshot(comfy_path="/c"),
        )
        self.assertFalse(ready)
        self.assertIn("incomplete", summary.lower())


class JsonProbeTests(unittest.TestCase):
    def test_parse_last_good_object(self):
        raw = "{not json\n" + json.dumps({"ok": True, "cosine": 0.99})
        data = _parse_json_line(raw)
        self.assertIsNotNone(data)
        self.assertTrue(data["ok"])

    def test_parse_all_bad(self):
        self.assertIsNone(_parse_json_line("{bad\n{also bad"))


class WheelSortAndBadVersionTests(unittest.TestCase):
    def test_version_tuple_post10(self):
        self.assertGreater(
            parse_version_tuple("2.2.0.post10"),
            parse_version_tuple("2.2.0.post6"),
        )

    def test_known_bad_exact(self):
        self.assertTrue(is_known_bad_version("2.2.0.post5"))
        self.assertFalse(is_known_bad_version("2.2.0.post50"))
        self.assertFalse(is_known_bad_version("2.2.0.post6"))

    def test_py39_excluded_from_post6(self):
        env = EnvSnapshot(
            comfy_path="/c",
            python_version="3.9.18",
            torch_version="2.12.0+cu130",
            torch_cuda="13.0",
            torch_cuda_available=True,
        )
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNone(match)


class InstallRepairTests(unittest.TestCase):
    def test_wrong_location_forces_repair(self):
        env = EnvSnapshot(
            comfy_path="/ComfyUI",
            python_path="/ComfyUI/python_embeded/python.exe",
            python_prefix="/ComfyUI/python_embeded",
            site_packages=["/ComfyUI/python_embeded/Lib/site-packages"],
            python_version="3.12.0",
            torch_version="2.9.1+cu128",
            torch_cuda="12.8",
            torch_cuda_available=True,
            sageattention_version="2.2.0.post6",
            sageattention_location="/Users/me/AppData/Roaming/Python/site-packages/sageattention/__init__.py",
        )
        plan = plan_install(env, host_platform="windows")
        self.assertTrue(_should_force_repair(env, plan))

    def test_dry_run_does_not_hold_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("#\n", encoding="utf-8")
            held = _install_lock.acquire(blocking=False)
            self.assertTrue(held)
            try:
                # dry_run should not contend for the exclusive lock
                with self.assertRaises(RuntimeError):
                    # still fails for missing CUDA torch, but must not be lock error
                    install_stack(str(root), dry_run=True)
            finally:
                _install_lock.release()

    def test_lock_blocks_real_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("#\n", encoding="utf-8")
            results: list[str] = []

            def worker():
                try:
                    install_stack(str(root), dry_run=False)
                    results.append("ok")
                except Exception as exc:  # noqa: BLE001
                    results.append(str(exc))

            self.assertTrue(_install_lock.acquire(blocking=False))
            try:
                t = threading.Thread(target=worker)
                t.start()
                t.join(timeout=3)
            finally:
                _install_lock.release()
            self.assertTrue(any("already running" in r for r in results))


class HelperScriptTests(unittest.TestCase):
    def test_backup_on_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("#\n", encoding="utf-8")
            helper = root / "run_sage_attention.sh"
            helper.write_text("OLD\n", encoding="utf-8")
            with patch(
                "sage_ready.install.resolve_environment",
                return_value=EnvSnapshot(
                    comfy_path=str(root),
                    main_py=str(root / "main.py"),
                    python_path=sys.executable,
                    platform="linux",
                ),
            ):
                path = write_launch_helper(str(root))
            self.assertTrue(Path(path).exists())
            self.assertTrue((root / "run_sage_attention.sh.bak").exists())
            self.assertEqual(
                (root / "run_sage_attention.sh.bak").read_text(encoding="utf-8"),
                "OLD\n",
            )


class LaunchScriptScopeTests(unittest.TestCase):
    def test_ignores_unrelated_parent_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            comfy = parent / "ComfyUI"
            comfy.mkdir()
            main = comfy / "main.py"
            main.write_text("#\n", encoding="utf-8")
            unrelated = parent / "notes.sh"
            unrelated.write_text("echo --use-sage-attention\n", encoding="utf-8")
            scripts = find_launch_scripts(comfy, main)
            self.assertNotIn(str(unrelated), scripts)


class ApiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_blank_path_rejected(self):
        r = self.client.post("/api/scan", json={"comfy_path": "   "})
        self.assertEqual(r.status_code, 422)

    def test_health_version(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["version"], "1.2.0")

    def test_verify_bad_json_does_not_500(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("#\n", encoding="utf-8")
            with patch(
                "sage_ready.verify.resolve_environment",
                return_value=EnvSnapshot(
                    comfy_path=str(root),
                    python_path=sys.executable,
                    platform="linux",
                ),
            ), patch("sage_ready.verify.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "{not-json\n"
                run.return_value.stderr = ""
                result = verify_kernel(str(root))
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
