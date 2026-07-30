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


if __name__ == "__main__":
    unittest.main()
