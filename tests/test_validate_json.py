import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
MODULE_PATH = (
    ROOT
    / "plugins"
    / "deep-research"
    / "source"
    / "skills"
    / "research"
    / "validate_json.py"
)
SPEC = importlib.util.spec_from_file_location("validate_json", MODULE_PATH)
validate_json = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_json)


class LoadFieldsYamlTests(unittest.TestCase):
    def load(self, fixture):
        return validate_json.load_fields_yaml(FIXTURES / fixture)

    def test_loads_field_categories_and_explicit_optional_fields(self):
        all_fields, required_fields, categories = self.load("field_categories.yaml")

        self.assertEqual(all_fields, {"name", "founded", "score"})
        self.assertEqual(required_fields, {"name", "score"})
        self.assertEqual(
            categories,
            {
                "name": "Identity Details",
                "founded": "Identity Details",
                "score": "Measured Results",
            },
        )

    def test_loads_categorized_fields_mapping(self):
        all_fields, required_fields, categories = self.load(
            "categorized_fields.yaml"
        )

        self.assertEqual(all_fields, {"name", "website", "score"})
        self.assertEqual(required_fields, all_fields)
        self.assertEqual(categories["website"], "Basic Details")
        self.assertEqual(categories["score"], "Metrics")

    def test_loads_flat_fields_list_as_uncategorized(self):
        all_fields, required_fields, categories = self.load("flat_fields.yaml")

        self.assertEqual(all_fields, {"name", "website"})
        self.assertEqual(required_fields, all_fields)
        self.assertEqual(set(categories.values()), {"(uncategorized)"})

    def test_empty_and_malformed_definitions_are_rejected(self):
        for fixture in ("empty_fields.yaml", "malformed_fields.yaml"):
            with self.subTest(fixture=fixture):
                with self.assertRaisesRegex(ValueError, "No field definitions"):
                    self.load(fixture)

    def test_non_mapping_roots_are_rejected(self):
        for content in ("- name: field\n", "0\n"):
            with self.subTest(content=content):
                with tempfile.TemporaryDirectory() as directory:
                    fields_path = Path(directory) / "fields.yaml"
                    fields_path.write_text(content, encoding="utf-8")

                    with self.assertRaisesRegex(
                        ValueError, "fields.yaml root must be a mapping"
                    ):
                        validate_json.load_fields_yaml(fields_path)

    def test_cli_reports_non_mapping_roots_without_traceback(self):
        for content in ("- name: field\n", "0\n"):
            with self.subTest(content=content):
                with tempfile.TemporaryDirectory() as directory:
                    fields_path = Path(directory) / "fields.yaml"
                    fields_path.write_text(content, encoding="utf-8")
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(MODULE_PATH),
                            "--fields",
                            str(fields_path),
                        ],
                        text=True,
                        capture_output=True,
                    )

                self.assertEqual(completed.returncode, 1)
                self.assertIn(
                    "[ERROR] fields.yaml root must be a mapping", completed.stdout
                )
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)


class ValidateJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (
            cls.all_fields,
            cls.required_fields,
            cls.categories,
        ) = validate_json.load_fields_yaml(FIXTURES / "field_categories.yaml")

    def test_complete_nested_declared_categories_pass(self):
        result = validate_json.validate_json(
            FIXTURES / "complete_nested.json",
            self.all_fields,
            self.required_fields,
            self.categories,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["covered"], 3)
        self.assertEqual(result["missing_required"], [])
        self.assertEqual(result["missing_optional"], [])
        self.assertEqual(result["coverage_rate"], 100.0)

    def test_missing_required_field_fails_but_optional_field_does_not(self):
        result = validate_json.validate_json(
            FIXTURES / "missing_required.json",
            self.all_fields,
            self.required_fields,
            self.categories,
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["missing_required"], ["score"])
        self.assertEqual(result["missing_optional"], ["founded"])
        self.assertEqual(
            result["missing_by_category"],
            {"Identity Details": ["founded"], "Measured Results": ["score"]},
        )

    def test_missing_only_explicitly_optional_field_passes(self):
        result = validate_json.validate_json(
            FIXTURES / "missing_optional.json",
            self.all_fields,
            self.required_fields,
            self.categories,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_required"], [])
        self.assertEqual(result["missing_optional"], ["founded"])

    def test_cli_fails_when_requested_json_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--fields",
                    str(FIXTURES / "field_categories.yaml"),
                    "--json",
                    str(missing),
                ],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("File not found", completed.stdout)

    def test_cli_does_not_discover_fields_for_explicit_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "fields.yaml").write_text(
                (FIXTURES / "field_categories.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            worktree = project / "worktree"
            worktree.mkdir()
            missing = worktree / "missing-fields.yaml"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--fields",
                    str(missing),
                    "--json",
                    str(FIXTURES / "complete_nested.json"),
                ],
                cwd=worktree,
                text=True,
                capture_output=True,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn(f"[ERROR] fields.yaml not found: {missing}", completed.stdout)

    def test_cli_discovers_fields_when_option_is_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            fields = project / "fields.yaml"
            fields.write_text(
                (FIXTURES / "field_categories.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            worktree = project / "worktree"
            worktree.mkdir()

            for cwd in (project, worktree):
                with self.subTest(cwd=cwd):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(MODULE_PATH),
                            "--json",
                            str(FIXTURES / "complete_nested.json"),
                        ],
                        cwd=cwd,
                        text=True,
                        capture_output=True,
                    )

                    self.assertEqual(completed.returncode, 0, completed.stdout)
                    self.assertIn("Field definition file:", completed.stdout)

    def test_cli_reports_malformed_json_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.json"
            malformed.write_text('{"name":', encoding="utf-8")
            invocations = (
                ["--json", str(malformed)],
                ["--dir", directory],
            )

            for input_args in invocations:
                with self.subTest(input_args=input_args):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(MODULE_PATH),
                            "--fields",
                            str(FIXTURES / "field_categories.yaml"),
                            *input_args,
                        ],
                        text=True,
                        capture_output=True,
                    )

                    self.assertEqual(completed.returncode, 1)
                    self.assertIn(
                        f"[ERROR] Invalid JSON in {malformed}", completed.stdout
                    )
                    self.assertNotIn(
                        "Traceback", completed.stdout + completed.stderr
                    )


if __name__ == "__main__":
    unittest.main()
