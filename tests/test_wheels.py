"""Unit tests for wheel matching and path helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sage_ready.detect import find_main_py, normalize_comfy_path
from sage_ready.models import EnvSnapshot
from sage_ready.wheels import (
    build_wheel_url,
    cuda_code_from_env,
    find_matching_wheel,
    is_known_bad_version,
    parse_torch_version,
    plan_install,
    triton_constraint_for_torch,
)


class ParseTorchTests(unittest.TestCase):
    def test_parse_cuda_local(self):
        full, mm, cuda = parse_torch_version("2.9.1+cu128")
        self.assertEqual(full, "2.9.1")
        self.assertEqual(mm, "2.9")
        self.assertEqual(cuda, "128")

    def test_triton_constraint(self):
        self.assertEqual(triton_constraint_for_torch("2.10.0+cu128"), ">=3.6,<4")
        self.assertEqual(triton_constraint_for_torch("2.7.1+cu128"), ">=3.3,<3.4")


class WheelMatchTests(unittest.TestCase):
    def _env(self, **kwargs):
        base = dict(
            comfy_path="/tmp/ComfyUI",
            python_version="3.12.0",
            torch_version="2.9.1+cu128",
            torch_cuda="12.8",
            torch_cuda_available=True,
            platform="windows",
        )
        base.update(kwargs)
        return EnvSnapshot(**base)

    def test_post6_for_torch_213(self):
        env = self._env(torch_version="2.13.0+cu130", torch_cuda="13.0")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["sage_ver"], "2.2.0.post6")
        self.assertIn("post6", match["wheel_url"])

    def test_cuda_alias_129_to_128(self):
        env = self._env(torch_version="2.9.0+cu129", torch_cuda="12.9")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["matched_cuda"], "128")

    def test_cuda_alias_132_to_130(self):
        env = self._env(torch_version="2.12.0+cu132", torch_cuda="13.2", python_version="3.11.0")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["sage_ver"], "2.2.0.post6")
        self.assertEqual(match["matched_cuda"], "130")

    def test_post3_for_torch_27(self):
        env = self._env(torch_version="2.7.1+cu128", torch_cuda="12.8")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["sage_ver"], "2.2.0.post3")

    def test_linux_plan_fallback_strategy(self):
        env = self._env()
        plan = plan_install(env, host_platform="linux")
        self.assertEqual(plan.strategy, "pip_sa2_or_fallback")
        self.assertEqual(plan.triton_package, "triton")

    def test_windows_plan_wheel(self):
        env = self._env()
        plan = plan_install(env, host_platform="windows")
        self.assertEqual(plan.strategy, "wheel")
        self.assertTrue(plan.wheel_url.startswith("https://github.com/woct0rdho"))

    def test_build_wheel_url_abi3(self):
        url = build_wheel_url(
            {
                "sage_ver": "2.2.0.post6",
                "cuda": "130",
                "torch_pattern": "2.12",
                "py_spec": "310",
                "tag": "v2.2.0-windows.post6",
                "abi3": True,
                "torch_filename_ver": "2.10.0andhigher",
            }
        )
        self.assertTrue(url.endswith(
            "sageattention-2.2.0+cu130torch2.10.0andhigher.post6-cp310-abi3-win_amd64.whl"
        ))

    def test_known_bad(self):
        self.assertTrue(is_known_bad_version("2.2.0.post5"))
        self.assertFalse(is_known_bad_version("2.2.0.post6"))

    def test_cuda_code_from_env(self):
        env = self._env(torch_version="2.9.1+cu128")
        self.assertEqual(cuda_code_from_env(env), "128")


class PathTests(unittest.TestCase):
    def test_find_main_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.py"
            main.write_text("# comfy\n", encoding="utf-8")
            self.assertEqual(find_main_py(root), main)

    def test_nested_comfyui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "ComfyUI"
            nested.mkdir()
            main = nested / "main.py"
            main.write_text("# comfy\n", encoding="utf-8")
            self.assertEqual(find_main_py(root), main)

    def test_normalize_main_py_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.py"
            main.write_text("# comfy\n", encoding="utf-8")
            self.assertEqual(normalize_comfy_path(str(main)), root.resolve())


class CheckSummaryTests(unittest.TestCase):
    def test_summarize_ready(self):
        from sage_ready.checks import summarize
        from sage_ready.models import CheckItem, CheckStatus

        checks = [
            CheckItem(id="comfy_root", title="c", status=CheckStatus.OK),
            CheckItem(id="python", title="p", status=CheckStatus.OK),
            CheckItem(id="torch", title="t", status=CheckStatus.OK),
            CheckItem(id="triton", title="tr", status=CheckStatus.OK),
            CheckItem(id="sageattention", title="s", status=CheckStatus.OK),
            CheckItem(id="kernel_test", title="k", status=CheckStatus.OK),
            CheckItem(id="launch_flag", title="l", status=CheckStatus.WARN),
        ]
        ready_for_install, ready, summary = summarize(checks)
        self.assertTrue(ready_for_install)
        self.assertTrue(ready)
        self.assertIn("ready", summary.lower())


if __name__ == "__main__":
    unittest.main()
