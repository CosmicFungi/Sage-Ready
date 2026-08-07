"""Unit tests for wheel matching, path helpers, and readiness gating."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sage_ready.checks import build_checks, package_in_target_env, summarize
from sage_ready.detect import find_main_py, normalize_comfy_path, resolve_python
from sage_ready.models import CheckItem, CheckStatus, EnvSnapshot
from sage_ready.versioning import parse_version_tuple, version_less_than
from sage_ready.wheels import (
    build_wheel_url,
    cuda_code_from_env,
    find_matching_wheel,
    is_allowed_wheel_url,
    is_known_bad_version,
    needs_version_upgrade,
    parse_torch_version,
    plan_install,
    preferred_sa_version,
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


class VersioningTests(unittest.TestCase):
    def test_parse_post(self):
        self.assertEqual(parse_version_tuple("2.2.0.post6"), (2, 2, 0, 6))
        self.assertTrue(version_less_than("2.2.0.post5", "2.2.0.post6"))
        self.assertFalse(version_less_than("2.2.0.post6", "2.2.0.post6"))

    def test_wheel_local_tag_equals_post6(self):
        from sage_ready.versioning import normalize_sage_version, versions_equivalent

        wheel_ver = "2.2.0+cu130torch2.10.0andhigher.post6"
        self.assertEqual(normalize_sage_version(wheel_ver), "2.2.0.post6")
        self.assertTrue(versions_equivalent(wheel_ver, "2.2.0.post6"))
        self.assertFalse(version_less_than(wheel_ver, "2.2.0.post6"))
        self.assertEqual(
            parse_version_tuple(wheel_ver), parse_version_tuple("2.2.0.post6")
        )

    def test_needs_upgrade_false_for_installed_post6_wheel(self):
        env = EnvSnapshot(
            comfy_path="/c",
            python_version="3.12.0",
            torch_version="2.12.0+cu130",
            torch_cuda="13.0",
            torch_cuda_available=True,
            sageattention_version="2.2.0+cu130torch2.10.0andhigher.post6",
        )
        plan = plan_install(env, host_platform="windows")
        self.assertEqual(plan.sage_version, "2.2.0.post6")
        self.assertFalse(needs_version_upgrade(env, plan))
        self.assertFalse(is_known_bad_version(env.sageattention_version))


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

    def test_prefers_post6_over_post4_for_torch_29(self):
        env = self._env(torch_version="2.9.1+cu128", torch_cuda="12.8")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["sage_ver"], "2.2.0.post6")

    def test_cuda_alias_129_to_128(self):
        env = self._env(torch_version="2.9.0+cu129", torch_cuda="12.9")
        match = find_matching_wheel(env, host_platform="windows")
        self.assertIsNotNone(match)
        self.assertEqual(match["matched_cuda"], "128")

    def test_cuda_alias_132_to_130(self):
        env = self._env(
            torch_version="2.12.0+cu132", torch_cuda="13.2", python_version="3.11.0"
        )
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
        self.assertEqual(plan.sage_version, "2.2.0")
        self.assertEqual(plan.package_spec, "sageattention==2.2.0")
        self.assertIn("Linux", plan.notes)

    def test_linux_plan_torch_214_cu132(self):
        env = self._env(
            torch_version="2.14.0+cu132",
            torch_cuda="13.2",
            python_version="3.12.0",
        )
        plan = plan_install(env, host_platform="linux")
        self.assertEqual(plan.strategy, "pip_sa2_or_fallback")
        self.assertEqual(plan.sage_version, "2.2.0")
        self.assertEqual(plan.package_spec, "sageattention==2.2.0")
        self.assertEqual(plan.triton_package, "triton")
        self.assertEqual(plan.triton_constraint, ">=3.6,<4")
        self.assertIn("Linux", plan.notes)
        self.assertIn("2.14", plan.notes)
        self.assertIn("132", plan.notes)
        self.assertIn("130", plan.notes)
        self.assertIn("Hugging Face", plan.notes)
        self.assertIsNone(plan.wheel_url)

    def test_linux_needs_upgrade_from_106(self):
        env = self._env(sageattention_version="1.0.6")
        plan = plan_install(env, host_platform="linux")
        self.assertTrue(needs_version_upgrade(env, plan))
        env2 = self._env(sageattention_version="2.2.0")
        self.assertFalse(needs_version_upgrade(env2, plan))

    def test_windows_plan_no_match_for_torch_214(self):
        env = self._env(
            torch_version="2.14.0+cu132",
            torch_cuda="13.2",
            python_version="3.12.0",
        )
        plan = plan_install(env, host_platform="windows")
        self.assertEqual(plan.strategy, "fallback_pypi")
        self.assertIn("2.14", plan.notes)
        self.assertIn("2.13", plan.notes)

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
        self.assertTrue(
            url.endswith(
                "sageattention-2.2.0+cu130torch2.10.0andhigher.post6-cp310-abi3-win_amd64.whl"
            )
        )

    def test_allowed_wheel_url(self):
        good = (
            "https://github.com/woct0rdho/SageAttention/releases/download/"
            "v2.2.0-windows.post6/sageattention-2.2.0+cu130torch2.10.0andhigher.post6-cp310-abi3-win_amd64.whl"
        )
        self.assertTrue(is_allowed_wheel_url(good))
        self.assertFalse(is_allowed_wheel_url("https://evil.example/x.whl"))

    def test_known_bad(self):
        self.assertTrue(is_known_bad_version("2.2.0.post5"))
        self.assertFalse(is_known_bad_version("2.2.0.post6"))

    def test_needs_upgrade(self):
        env = self._env(sageattention_version="2.2.0.post3")
        plan = plan_install(env, host_platform="windows")
        self.assertTrue(needs_version_upgrade(env, plan))
        env2 = self._env(sageattention_version=plan.sage_version)
        self.assertFalse(needs_version_upgrade(env2, plan))

    def test_preferred_min(self):
        self.assertEqual(preferred_sa_version(), "2.2.0.post6")

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

    def test_resolve_python_prefers_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.py"
            main.write_text("# comfy\n", encoding="utf-8")
            if sys.platform.startswith("win"):
                emb = root / "python_embeded"
                emb.mkdir()
                py = emb / "python.exe"
                py.write_text("", encoding="utf-8")
            else:
                # Simulate portable candidate absent; create local venv python
                venv_bin = root / ".venv" / "bin"
                venv_bin.mkdir(parents=True)
                py = venv_bin / "python"
                py.write_text("#!/bin/sh\n", encoding="utf-8")
                py.chmod(0o755)

            with patch("sage_ready.detect._has_torch", return_value=True):
                env_type, path, fallback = resolve_python(root, main)
            self.assertFalse(fallback)
            self.assertIn(env_type, {"portable", "venv"})
            self.assertEqual(path, py.resolve())

    def test_linux_ignores_unrelated_parent_venv(self):
        if sys.platform.startswith("win"):
            self.skipTest("Linux-focused discovery test")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # Unrelated parent .venv (like $HOME/.venv)
            rogue = home / ".venv" / "bin"
            rogue.mkdir(parents=True)
            rogue_py = rogue / "python"
            rogue_py.write_text("#!/bin/sh\n", encoding="utf-8")
            rogue_py.chmod(0o755)

            comfy = home / "ComfyUI"
            comfy.mkdir()
            main = comfy / "main.py"
            main.write_text("# comfy\n", encoding="utf-8")

            with patch("sage_ready.detect._has_torch", return_value=True):
                env_type, path, fallback = resolve_python(comfy, main)
            # Must fall back to system/active — not the home .venv as a trusted venv
            self.assertTrue(fallback)
            self.assertNotEqual(path, rogue_py.resolve())
            self.assertNotEqual(env_type, "venv")


class PackageLocationTests(unittest.TestCase):
    def test_package_in_prefix(self):
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
                "/Users/me/AppData/Roaming/Python/site-packages/sageattention/__init__.py",
                env,
            )
        )


class CheckSummaryTests(unittest.TestCase):
    def _ok_checks(self, **overrides):
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
        return [
            CheckItem(id=k, title=k, status=v) for k, v in items.items()
        ]

    def test_summarize_ready(self):
        env = EnvSnapshot(comfy_path="/c", python_is_fallback=False)
        ready_for_install, ready, summary = summarize(self._ok_checks(), env)
        self.assertTrue(ready_for_install)
        self.assertTrue(ready)
        self.assertIn("ready", summary.lower())

    def test_kernel_skip_not_ready(self):
        env = EnvSnapshot(comfy_path="/c")
        _, ready, _ = summarize(
            self._ok_checks(kernel_test=CheckStatus.SKIP), env
        )
        self.assertFalse(ready)

    def test_post5_warn_not_ready(self):
        env = EnvSnapshot(comfy_path="/c")
        _, ready, summary = summarize(
            self._ok_checks(
                sageattention=CheckStatus.WARN,
                sa_version=CheckStatus.WARN,
            ),
            env,
        )
        self.assertFalse(ready)
        self.assertIn("Almost ready", summary)

    def test_fallback_python_blocks_ready(self):
        env = EnvSnapshot(comfy_path="/c", python_is_fallback=True)
        _, ready, _ = summarize(self._ok_checks(), env)
        self.assertFalse(ready)

    def test_linux_wheel_match_ok_when_sa2_installed(self):
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

    def test_linux_wheel_match_warn_on_106(self):
        env = EnvSnapshot(
            comfy_path="/home/you/ComfyUI",
            python_path="/home/you/ComfyUI/.venv/bin/python",
            python_version="3.12.0",
            platform="linux",
            torch_version="2.14.0+cu132",
            torch_cuda="13.2",
            torch_cuda_available=True,
            sageattention_version="1.0.6",
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
        self.assertEqual(by_id["wheel_match"].status, CheckStatus.WARN)
        self.assertEqual(by_id["sa_version"].status, CheckStatus.WARN)


if __name__ == "__main__":
    unittest.main()
