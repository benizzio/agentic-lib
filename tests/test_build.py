from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build", ROOT / "scripts" / "build.py")
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
os.sys.modules[SPEC.name] = build
SPEC.loader.exec_module(build)


PLUGIN = """\
schema_version: 1
package:
  version: 1.2.3
  description: Test plugin.
  author: tester
  license: MIT
  repository: https://example.test/repo
artifacts:
  - source: source/agent.md
    destination: .apm/agents/example.agent.md
    frontmatter: true
  - source: source/skills/
    destination: .apm/skills/
    frontmatter_glob: "**/SKILL.md"
  - source: source/resources/
    destination: .apm/skills/example/references/
"""

TARGET = """\
schema_version: 1
target: alpha
package_name: example-alpha
frontmatter:
  source/agent.md:
    shared: null
    tools:
      - read
tests:
  project_paths:
    - .agents/example.md
  global_paths:
    - .config/example.md
"""


class BuilderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        plugin = self.root / "plugins" / "example"
        (plugin / "targets").mkdir(parents=True)
        (plugin / "source" / "skills" / "example").mkdir(parents=True)
        (plugin / "source" / "resources").mkdir(parents=True)
        (plugin / "plugin.yml").write_text(PLUGIN, encoding="utf-8")
        (plugin / "targets" / "alpha.yml").write_text(TARGET, encoding="utf-8")
        (plugin / "source" / "agent.md").write_text(
            "---\r\nname: example\r\nshared:\r\n  old: true\r\n---\r\nBody {topic}\r\n\r\n",
            encoding="utf-8",
        )
        (plugin / "source" / "skills" / "example" / "SKILL.md").write_text(
            "---\nname: example\ndescription: Example skill.\n---\nSkill body.\n", encoding="utf-8"
        )
        (plugin / "source" / "resources" / "guide.md").write_text(
            "Guide.\r\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @property
    def plugin(self) -> Path:
        return self.root / "plugins" / "example"

    def write_plugin(self, content: str) -> None:
        (self.plugin / "plugin.yml").write_text(content, encoding="utf-8")

    def write_target(self, content: str) -> None:
        (self.plugin / "targets" / "alpha.yml").write_text(content, encoding="utf-8")

    def generated(self) -> dict:
        return dict(build.generate_all(self.root).files)

    def test_discovers_plugin_and_target(self) -> None:
        plugins = build.discover_plugins(self.root)
        self.assertEqual([item.name for item in plugins], ["example"])
        self.assertEqual([item.name for item in plugins[0].targets], ["alpha"])

    def test_generation_is_deterministic_and_normalized(self) -> None:
        first = self.generated()
        second = self.generated()
        self.assertEqual(first, second)
        agent = first[build.PurePosixPath("example/alpha/.apm/agents/example.agent.md")]
        self.assertNotIn(b"\r", agent)
        self.assertTrue(agent.endswith(b"\n"))
        self.assertFalse(agent.endswith(b"\n\n"))
        self.assertIn(b"Body {topic}", agent)

    def test_overlay_replaces_top_level_and_null_deletes(self) -> None:
        agent = self.generated()[build.PurePosixPath("example/alpha/.apm/agents/example.agent.md")]
        frontmatter, body = build._load_frontmatter(build.PurePosixPath("agent.md"), agent)
        self.assertNotIn("shared", frontmatter)
        self.assertEqual(frontmatter["tools"], ["read"])
        self.assertEqual(body, "Body {topic}\n")

    def test_generated_comments_and_manifest(self) -> None:
        files = self.generated()
        agent = files[build.PurePosixPath("example/alpha/.apm/agents/example.agent.md")]
        skill = files[build.PurePosixPath("example/alpha/.apm/skills/example/SKILL.md")]
        manifest = files[build.PurePosixPath("example/alpha/apm.yml")]
        self.assertIn(b"# Generated from source/agent.md; do not edit.", agent)
        self.assertIn(b"# Generated from source/skills/example/SKILL.md; do not edit.", skill)
        self.assertIn(b'version: "1.2.3"', manifest)
        self.assertIn(b"name: example-alpha", manifest)
        self.assertIn(b"- .apm/agents/", manifest)
        self.assertIn(b"- .apm/skills/", manifest)

    def test_top_level_apm_file_is_generated_and_included_as_a_file(self) -> None:
        self.write_plugin(
            PLUGIN
            + """\
  - source: source/AGENTS.md
    destination: .apm/AGENTS.md
"""
        )
        (self.plugin / "source" / "AGENTS.md").write_text("Instructions.\n", encoding="utf-8")

        files = self.generated()
        generated = files[build.PurePosixPath("example/alpha/.apm/AGENTS.md")]
        manifest = files[build.PurePosixPath("example/alpha/apm.yml")]
        self.assertEqual(generated, b"Instructions.\n")
        self.assertIn(b"- .apm/AGENTS.md\n", manifest)
        self.assertNotIn(b"- .apm/AGENTS.md/", manifest)

    def test_directory_resources_are_copied(self) -> None:
        guide = self.generated()[
            build.PurePosixPath("example/alpha/.apm/skills/example/references/guide.md")
        ]
        self.assertEqual(guide, b"Guide.\n")

    def test_python_cache_artifacts_are_not_copied(self) -> None:
        cache = self.plugin / "source" / "skills" / "example" / "__pycache__"
        cache.mkdir()
        (cache / "helper.pyc").write_bytes(b"bytecode")
        paths = {path.as_posix() for path in self.generated()}
        self.assertFalse(any("__pycache__" in path or path.endswith(".pyc") for path in paths))

    def test_unknown_plugin_and_target_keys_fail(self) -> None:
        self.write_plugin(PLUGIN + "unknown: true\n")
        with self.assertRaisesRegex(build.BuildError, "unknown key"):
            build.generate_all(self.root)
        self.write_plugin(PLUGIN)
        self.write_target(TARGET + "unknown: true\n")
        with self.assertRaisesRegex(build.BuildError, "unknown key"):
            build.generate_all(self.root)

    def test_duplicate_yaml_key_fails(self) -> None:
        self.write_plugin(PLUGIN.replace("schema_version: 1", "schema_version: 1\nschema_version: 1"))
        with self.assertRaisesRegex(build.BuildError, "duplicate key"):
            build.generate_all(self.root)

    def test_malformed_yaml_and_frontmatter_fail(self) -> None:
        self.write_target("schema_version: [\n")
        with self.assertRaisesRegex(build.BuildError, "invalid YAML"):
            build.generate_all(self.root)
        self.write_target(TARGET)
        (self.plugin / "source" / "agent.md").write_text("---\nname: [\n---\nBody\n", encoding="utf-8")
        with self.assertRaisesRegex(build.BuildError, "frontmatter"):
            build.generate_all(self.root)

    def test_missing_source_fails(self) -> None:
        (self.plugin / "source" / "agent.md").unlink()
        with self.assertRaisesRegex(build.BuildError, "source does not exist"):
            build.generate_all(self.root)

    def test_absolute_traversal_and_outside_destination_fail(self) -> None:
        for old, new in (
            ("source/agent.md", "/tmp/agent.md"),
            ("source/agent.md", "../agent.md"),
            (".apm/agents/example.agent.md", "output/agent.md"),
        ):
            with self.subTest(path=new):
                self.write_plugin(PLUGIN.replace(old, new, 1))
                with self.assertRaises(build.BuildError):
                    build.generate_all(self.root)
        self.write_plugin(PLUGIN)

    def test_duplicate_destination_fails(self) -> None:
        duplicate = """
  - source: source/agent.md
    destination: .apm/agents/example.agent.md
    frontmatter: true
"""
        self.write_plugin(PLUGIN + duplicate)
        with self.assertRaisesRegex(build.BuildError, "duplicate destination"):
            build.generate_all(self.root)

    def test_unknown_overlay_source_fails(self) -> None:
        self.write_target(TARGET.replace("source/agent.md:", "source/missing.md:"))
        with self.assertRaisesRegex(build.BuildError, "unknown or ineligible"):
            build.generate_all(self.root)

    def test_unresolved_generator_marker_fails(self) -> None:
        (self.plugin / "source" / "resources" / "guide.md").write_text(
            "@@GENERATOR:value@@\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(build.BuildError, "unresolved generator marker"):
            build.generate_all(self.root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_source_and_nested_symlink_fail(self) -> None:
        outside = self.root / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        agent = self.plugin / "source" / "agent.md"
        agent.unlink()
        agent.symlink_to(outside)
        with self.assertRaisesRegex(build.BuildError, "symlink"):
            build.generate_all(self.root)
        agent.unlink()
        agent.write_text("---\nname: example\nshared: yes\n---\nBody\n", encoding="utf-8")
        (self.plugin / "source" / "resources" / "link.md").symlink_to(outside)
        with self.assertRaisesRegex(build.BuildError, "symlink"):
            build.generate_all(self.root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_plugin_config_and_packages_root_fail(self) -> None:
        config = self.plugin / "plugin.yml"
        real_config = self.plugin / "plugin-real.yml"
        config.rename(real_config)
        config.symlink_to(real_config.name)
        with self.assertRaisesRegex(build.BuildError, "symlinked plugin"):
            build.generate_all(self.root)
        config.unlink()
        real_config.rename(config)

        outside = self.root / "outside-packages"
        outside.mkdir()
        packages = self.root / "packages"
        packages.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(build.BuildError, "packages root"):
            build.build_all(self.root)

    def test_build_replaces_tree_and_removes_stale_files(self) -> None:
        stale = self.root / "packages" / "plugins" / "stale" / "old.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("old", encoding="utf-8")
        build.build_all(self.root)
        self.assertFalse(stale.exists())
        self.assertTrue(
            (self.root / "packages/plugins/example/alpha/.apm/agents/example.agent.md").is_file()
        )
        self.assertFalse(list((self.root / "packages").glob(".plugins.*-*")))

    def test_generation_failure_leaves_existing_output_unchanged(self) -> None:
        existing = self.root / "packages" / "plugins" / "keep.txt"
        existing.parent.mkdir(parents=True)
        existing.write_text("keep", encoding="utf-8")
        (self.plugin / "source" / "agent.md").unlink()
        with self.assertRaises(build.BuildError):
            build.build_all(self.root)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

    def test_check_reports_missing_changed_and_extra_without_writing(self) -> None:
        build.build_all(self.root)
        output = self.root / "packages" / "plugins"
        missing = output / "example/alpha/.apm/skills/example/SKILL.md"
        changed = output / "example/alpha/apm.yml"
        extra = output / "extra.txt"
        missing.unlink()
        changed.write_text("changed\n", encoding="utf-8")
        extra.write_text("extra\n", encoding="utf-8")
        before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
        report = build.check_all(self.root)
        after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(report.missing, (build.PurePosixPath("example/alpha/.apm/skills/example/SKILL.md"),))
        self.assertEqual(report.changed, (build.PurePosixPath("example/alpha/apm.yml"),))
        self.assertEqual(report.extra, (build.PurePosixPath("extra.txt"),))

    def test_check_succeeds_after_build(self) -> None:
        build.build_all(self.root)
        self.assertTrue(build.check_all(self.root).clean)

    def test_check_ignores_python_cache_artifacts_but_reports_other_extras(self) -> None:
        build.build_all(self.root)
        output = self.root / "packages" / "plugins"
        cache = output / "example" / "alpha" / "__pycache__"
        cache.mkdir()
        (cache / "helper.pyc").write_bytes(b"bytecode")
        (output / "helper.pyc").write_bytes(b"bytecode")
        (output / "helper.pyo").write_bytes(b"optimized bytecode")

        self.assertTrue(build.check_all(self.root).clean)

        (output / "extra.txt").write_text("extra\n", encoding="utf-8")
        self.assertEqual(
            build.check_all(self.root).extra,
            (build.PurePosixPath("extra.txt"),),
        )


if __name__ == "__main__":
    unittest.main()
