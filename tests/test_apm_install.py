from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_validate_packages import validate_packages


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apm_install", ROOT / "scripts/test_apm_install.py")
assert SPEC and SPEC.loader
install = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = install
SPEC.loader.exec_module(install)


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packages = validate_packages.discover_packages()

    def deploy_agents(self, package, root: Path, scope: str) -> None:
        files = install.installed_agents(package, scope)
        if package.plugin == "hyperfocus-review":
            files.update(install.installed_skill_files(package, scope))
        for destination, source in files.items():
            path = root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)

    def test_reviewer_install_needs_references_but_no_research_resources(self) -> None:
        for package in self.packages:
            if package.plugin != "hyperfocus-review":
                continue
            for scope in ("project", "global"):
                with self.subTest(target=package.target, scope=scope), tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    self.deploy_agents(package, root, scope)
                    install.assert_install(package, root, scope)
                    agent_root = root / install.TARGET_LAYOUTS[package.target][f"{scope}_agents"]
                    (agent_root / "unexpected.md").write_text("extra", encoding="utf-8")
                    with self.assertRaisesRegex(install.ValidationError, "agent set"):
                        install.assert_install(package, root, scope)

    def test_rejects_renamed_missing_and_modified_agents(self) -> None:
        package = next(p for p in self.packages if p.plugin == "hyperfocus-review" and p.target == "opencode")
        for mutation in ("rename", "missing", "body", "policy"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                self.deploy_agents(package, root, "project")
                path = root / next(iter(install.installed_agents(package, "project")))
                if mutation == "rename":
                    path.rename(path.with_name("other.md"))
                elif mutation == "missing":
                    path.unlink()
                elif mutation == "body":
                    path.write_text(path.read_text() + "Changed body.\n", encoding="utf-8")
                else:
                    path.write_text(path.read_text().replace("effect: deny", "effect: allow", 1), encoding="utf-8")
                with self.assertRaises(install.ValidationError):
                    install.assert_install(package, root, "project")

    def test_deep_research_resources_are_still_required(self) -> None:
        package = next(p for p in self.packages if p.plugin == "deep-research")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.deploy_agents(package, root, "project")
            with self.assertRaisesRegex(install.ValidationError, "missing"):
                install.assert_install(package, root, "project")

    def test_agent_only_global_install_is_direct(self) -> None:
        for package in self.packages:
            if package.plugin != "hyperfocus-review":
                continue
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                shutil.copytree(package.root / ".apm/agents", root / ".apm/agents")
                agent_only = validate_packages.Package(
                    package.plugin, package.target, root, package.config_path, package.config
                )
                self.assertEqual(
                    install.global_install_commands("apm", agent_only, root),
                    (["apm", "install", str(root.resolve()), "--target", package.target, "--global"],),
                )

    def test_reviewer_references_are_required_and_preserved(self) -> None:
        for package in self.packages:
            if package.plugin != "hyperfocus-review":
                continue
            for scope in ("project", "global"):
                for mutation in ("missing", "modified"):
                    with self.subTest(target=package.target, scope=scope, mutation=mutation), tempfile.TemporaryDirectory() as raw:
                        root = Path(raw)
                        self.deploy_agents(package, root, scope)
                        reference = next(
                            path for path in install.installed_skill_files(package, scope)
                            if path.name == "github.md"
                        )
                        if mutation == "missing":
                            (root / reference).unlink()
                        else:
                            (root / reference).write_text("Changed guide.\n", encoding="utf-8")
                        with self.assertRaises(install.ValidationError):
                            install.assert_install(package, root, scope)

    def test_reviewer_global_opencode_uses_shared_reference_workaround(self) -> None:
        package = next(p for p in self.packages if p.plugin == "hyperfocus-review" and p.target == "opencode")
        with tempfile.TemporaryDirectory() as raw:
            commands = install.global_install_commands("apm", package, Path(raw))
            self.assertEqual(len(commands), 2)
            self.assertIn("agent-skills", commands[0])
            self.assertIn("opencode", commands[1])

    def test_global_workaround_discovers_all_agents_and_preserves_version(self) -> None:
        original = next(p for p in self.packages if p.target == "opencode" and p.plugin == "deep-research")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package_root = root / "package"
            shutil.copytree(original.root, package_root)
            source = package_root / ".apm/agents/web-search.agent.md"
            shutil.copy2(source, source.with_name("second.agent.md"))
            package = validate_packages.Package("example", "opencode", package_root, original.config_path, {})
            commands = install.global_install_commands("apm", package, root)
            self.assertEqual(len(commands), 2)
            self.assertIn("agent-skills", commands[0])
            staged = root / "opencode-agent-package"
            self.assertEqual({p.name for p in (staged / ".apm/agents").glob("*.md")}, {"web-search.agent.md", "second.agent.md"})
            manifest = install.load_yaml_mapping(staged / "apm.yml")
            self.assertEqual(manifest["version"], install.load_yaml_mapping(original.root / "apm.yml")["version"])
            self.assertEqual(manifest["includes"], [".apm/agents/"])

    def test_research_regressions_run_only_for_deep_research(self) -> None:
        for package in self.packages:
            with self.subTest(plugin=package.plugin, target=package.target), tempfile.TemporaryDirectory() as raw:
                def fake_success(command, cwd, env):
                    if "--global" in command:
                        state = Path(env["HOME"]) / ".apm"
                        state.mkdir(exist_ok=True)
                        for name in ("apm.yml", "apm.lock.yaml"):
                            (state / name).touch()

                with mock.patch.object(install, "require_success", side_effect=fake_success), \
                     mock.patch.object(install, "assert_install"), \
                     mock.patch.object(install, "expected_paths", return_value=set()), \
                     mock.patch.object(install, "run_validator_regressions") as regressions:
                    install.test_package("apm", package, Path(raw))
                self.assertEqual(regressions.call_count, 2 if package.plugin == "deep-research" else 0)

    def test_environment_redirects_xdg_paths_into_temporary_home(self) -> None:
        env = install.isolated_env(Path("/tmp/opencode/test-home"))
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            self.assertTrue(env[key].startswith("/tmp/opencode/test-home"))


if __name__ == "__main__":
    unittest.main()
