from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_packages", ROOT / "scripts" / "validate_packages.py"
)
assert SPEC and SPEC.loader
validate_packages = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_packages
SPEC.loader.exec_module(validate_packages)


class ParseYamlMappingTests(unittest.TestCase):
    def test_supports_nested_flow_and_block_yaml(self) -> None:
        parsed = validate_packages.parse_yaml_mapping(
            """\
name: example
settings: {enabled: true, limits: [1, 2]}
items:
  - name: first
    tags: [one, two]
  - name: second
    notes: >-
      folded
      text
"""
        )

        self.assertEqual(parsed["settings"], {"enabled": True, "limits": [1, 2]})
        self.assertEqual(parsed["items"][0], {"name": "first", "tags": ["one", "two"]})
        self.assertEqual(parsed["items"][1]["notes"], "folded text")

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(validate_packages.ValidationError, "duplicate key"):
            validate_packages.parse_yaml_mapping("outer:\n  value: 1\n  value: 2\n")

    def test_rejects_aliases(self) -> None:
        with self.assertRaisesRegex(validate_packages.ValidationError, "aliases are not allowed"):
            validate_packages.parse_yaml_mapping("first: &value [1]\nsecond: *value\n")

    def test_rejects_multiple_documents(self) -> None:
        with self.assertRaisesRegex(validate_packages.ValidationError, "exactly one mapping"):
            validate_packages.parse_yaml_mapping("first: 1\n---\nsecond: 2\n")

    def test_rejects_non_mapping_root(self) -> None:
        with self.assertRaisesRegex(validate_packages.ValidationError, "exactly one mapping"):
            validate_packages.parse_yaml_mapping("[one, two]\n")


class FrontmatterTests(unittest.TestCase):
    def test_malformed_quoted_scalar_raises_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.md"
            path.write_text('---\nname: "unterminated\n---\nBody\n', encoding="utf-8")

            with self.assertRaisesRegex(validate_packages.ValidationError, "invalid YAML"):
                validate_packages.frontmatter(path)


class RunTests(unittest.TestCase):
    @mock.patch.object(validate_packages.subprocess, "run")
    def test_passes_timeout_on_success(self, run: mock.Mock) -> None:
        run.return_value = CompletedProcess(["apm", "audit"], 0, "output\n", "")

        result = validate_packages._run(["apm", "audit"], Path("/package"))

        self.assertIsNone(result)
        run.assert_called_once_with(
            ["apm", "audit"],
            cwd=Path("/package"),
            text=True,
            capture_output=True,
            timeout=validate_packages.COMMAND_TIMEOUT_SECONDS,
        )

    @mock.patch.object(validate_packages.subprocess, "run")
    def test_returns_error_when_command_times_out(self, run: mock.Mock) -> None:
        run.side_effect = TimeoutExpired(["apm", "audit"], 60)

        result = validate_packages._run(["apm", "audit"], Path("/package"))

        self.assertEqual(result, "command timed out after 60 seconds: apm audit")

    @mock.patch.object(validate_packages.subprocess, "run")
    def test_returns_error_when_executable_is_missing(self, run: mock.Mock) -> None:
        run.side_effect = FileNotFoundError(2, "No such file or directory", "apm")

        result = validate_packages._run(["apm", "audit"], Path("/package"))

        self.assertEqual(result, "command executable not found: apm")


class ContentChecksTests(unittest.TestCase):
    def test_rejects_claude_path_fragment_on_interior_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = root / ".apm" / "skills" / "example" / "notes.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("Before\n.claude/settings.json\nAfter\n", encoding="utf-8")
            package = validate_packages.Package(
                plugin="deep-research",
                target="opencode",
                root=root,
                config_path=root / "target.yml",
                config={},
            )

            errors = validate_packages._content_checks(package, root)

            self.assertIn(
                f"{markdown}: contains a Claude/Codex absolute-path fragment",
                errors,
            )


class ValidateTests(unittest.TestCase):
    @mock.patch.object(validate_packages, "_run", return_value=None)
    @mock.patch.object(validate_packages, "discover_packages")
    def test_uses_each_repo_root_without_mutating_default(
        self, discover_packages: mock.Mock, _run: mock.Mock
    ) -> None:
        original_repo_root = validate_packages.REPO_ROOT
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            first_root = parent / "first"
            second_root = parent / "second"
            packages = []
            for repo_root in (first_root, second_root):
                package_root = repo_root / "packages" / "plugins" / "example" / "opencode"
                agent = package_root / ".apm" / "agents" / "module.md"
                agent.parent.mkdir(parents=True)
                agent.write_text(
                    "---\nname: module\nmode: subagent\npermission: {}\n---\nBody\n",
                    encoding="utf-8",
                )
                packages.append(
                    validate_packages.Package(
                        plugin="example",
                        target="opencode",
                        root=package_root,
                        config_path=repo_root / "target.yml",
                        config={},
                    )
                )

            source_module = first_root / "plugins" / "example" / "source" / "modules" / "module.md"
            source_module.parent.mkdir(parents=True)
            source_module.write_text("source\n", encoding="utf-8")
            discover_packages.side_effect = ([packages[0]], [packages[1]])

            with mock.patch("builtins.print"):
                self.assertEqual(validate_packages.validate("apm", first_root), 1)
                self.assertEqual(validate_packages.validate("apm", second_root), 0)

        self.assertEqual(validate_packages.REPO_ROOT, original_repo_root)
        self.assertEqual(
            discover_packages.call_args_list,
            [mock.call(first_root), mock.call(second_root)],
        )


if __name__ == "__main__":
    unittest.main()
