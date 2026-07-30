from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
