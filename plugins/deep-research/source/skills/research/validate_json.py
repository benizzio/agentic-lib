#!/usr/bin/env python3

import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

CATEGORY_MAPPING = {
    "basic_info": ["basic_info", "Basic Info"],
    "technical_features": ["technical_features", "technical_characteristics", "Technical Features"],
    "performance_metrics": ["performance_metrics", "performance", "Performance Metrics"],
    "milestone_significance": ["milestone_significance", "milestones", "Milestone Significance"],
    "business_info": ["business_info", "commercial_info", "Business Info"],
    "competition_ecosystem": ["competition_ecosystem", "competition", "Competition Ecosystem"],
    "history": ["history", "History"],
    "market_positioning": ["market_positioning", "market", "Market Positioning"],
}

_SKIP_KEYS = {"_source_file", "uncertain"}


def _iter_field_defs(node, category="(uncategorized)"):
    """Yield field dictionaries and categories from an unknown schema."""
    if isinstance(node, dict):
        if isinstance(node.get("name"), (str, int, float)):
            yield node, category
            return
        for key, value in node.items():
            if key in _SKIP_KEYS:
                continue
            subcategory = category if key in ("fields", "field_categories") else str(key)
            yield from _iter_field_defs(value, subcategory)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_field_defs(item, category)


def load_fields_yaml(fields_path):
    """Parse supported fields.yaml forms and return field requirement metadata."""
    with fields_path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"fields.yaml root must be a mapping: {fields_path}")

    definitions = []

    def add(field, category):
        if isinstance(field, dict) and "name" in field:
            definitions.append(
                (str(field["name"]), str(category), field.get("required", None))
            )

    field_categories_node = data.get("field_categories")
    if isinstance(field_categories_node, list):
        for category in field_categories_node:
            if isinstance(category, dict):
                category_name = category.get("category", "(uncategorized)")
                for field in category.get("fields", []) or []:
                    add(field, category_name)

    if not definitions:
        fields_node = data.get("fields")
        if isinstance(fields_node, dict):
            for category_name, fields in fields_node.items():
                if isinstance(fields, list):
                    for field in fields:
                        add(field, category_name)
                else:
                    add(fields, category_name)
        elif isinstance(fields_node, list):
            for field in fields_node:
                add(field, "(uncategorized)")

    if not definitions:
        for field, category in _iter_field_defs(data):
            add(field, category)

    if not definitions:
        raise ValueError(f"No field definitions parsed from {fields_path}")

    all_fields = {name for name, _, _ in definitions}
    if any(required is not None for _, _, required in definitions):
        required_fields = {
            name for name, _, required in definitions if required
        }
    else:
        required_fields = set(all_fields)
    field_categories = {
        name: category for name, category, _ in definitions
    }
    return all_fields, required_fields, field_categories


def extract_json_fields(data, category_mapping=None, extra_nested_keys=None):
    category_mapping = CATEGORY_MAPPING if category_mapping is None else category_mapping
    nested_keys = {key for keys in category_mapping.values() for key in keys}
    if extra_nested_keys:
        nested_keys |= {str(key) for key in extra_nested_keys}
    fields = set()
    stack = [(data, True)]
    while stack:
        obj, is_category_level = stack.pop()
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in _SKIP_KEYS:
                    continue
                if is_category_level and key in nested_keys:
                    if isinstance(value, dict):
                        stack.append((value, True))
                    continue
                fields.add(key)
        elif isinstance(obj, list):
            stack.extend(
                (item, is_category_level)
                for item in obj
                if isinstance(item, dict)
            )
    return fields


def validate_json(json_path, all_fields, required_fields, field_categories):
    with json_path.open(encoding="utf-8") as file:
        data = json.load(file)
    json_fields = extract_json_fields(
        data, extra_nested_keys=set(field_categories.values())
    )
    covered = all_fields & json_fields
    missing = all_fields - json_fields
    extra = json_fields - all_fields
    missing_required = missing & required_fields
    missing_by_category = defaultdict(list)
    for field in missing:
        missing_by_category[field_categories.get(field, "Unknown")].append(field)
    return {
        "file": json_path.name,
        "total_defined": len(all_fields),
        "covered": len(covered),
        "missing": len(missing),
        "extra": len(extra),
        "coverage_rate": len(covered) / len(all_fields) * 100,
        "missing_required": sorted(missing_required),
        "missing_optional": sorted(missing - required_fields),
        "missing_by_category": {
            key: sorted(value) for key, value in missing_by_category.items()
        },
        "extra_fields": sorted(extra),
        "valid": len(missing_required) == 0,
    }


def print_result(result, verbose=True):
    status = "PASS" if result["valid"] else "FAIL"
    line = "=" * 60
    print(f"\n{line}")
    print(f"[{status}] {result['file']}")
    print(line)
    print(
        f"Coverage: {result['coverage_rate']:.1f}% "
        f"({result['covered']}/{result['total_defined']})"
    )
    if result["missing_required"]:
        print(
            f"\n[ERROR] Missing required fields "
            f"({len(result['missing_required'])}):"
        )
        print("\n".join(f"  - {field}" for field in result["missing_required"]))
    if verbose and result["missing_optional"]:
        missing_required = set(result["missing_required"])
        print(
            f"\n[WARN] Missing optional fields "
            f"({len(result['missing_optional'])}):"
        )
        for category in sorted(result["missing_by_category"]):
            optional = [
                field
                for field in result["missing_by_category"][category]
                if field not in missing_required
            ]
            if optional:
                print(f"  [{category}]: {', '.join(optional)}")
    if verbose and result["extra_fields"]:
        extra = result["extra_fields"]
        print(f"\n[INFO] Extra fields ({len(extra)}):")
        print(f"  {', '.join(extra[:10])}")
        if len(extra) > 10:
            print(f"  ... and {len(extra) - 10} more")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate whether JSON files cover all fields defined in fields.yaml"
    )
    parser.add_argument(
        "--fields", "-f", type=str, help="Path to fields.yaml", default="fields.yaml"
    )
    parser.add_argument(
        "--json", "-j", type=str, nargs="*", help="JSON file paths to validate"
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=str,
        help="Directory containing JSON files",
        default="results",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Show summary only")
    args = parser.parse_args()
    fields_path = Path(args.fields)
    if not fields_path.exists():
        for path in (Path.cwd() / "fields.yaml", Path.cwd().parent / "fields.yaml"):
            if path.exists():
                fields_path = path
                break
    if not fields_path.exists():
        print(f"[ERROR] fields.yaml not found: {fields_path}")
        sys.exit(1)
    print(f"Field definition file: {fields_path}")
    try:
        all_fields, required_fields, field_categories = load_fields_yaml(fields_path)
    except (ValueError, yaml.YAMLError) as error:
        print(f"[ERROR] {error}")
        sys.exit(1)
    print(
        f"Total fields: {len(all_fields)} "
        f"(required: {len(required_fields)}, "
        f"optional: {len(all_fields) - len(required_fields)})"
    )
    json_files = (
        [Path(path) for path in args.json]
        if args.json
        else sorted(Path(args.dir).glob("*.json"))
        if Path(args.dir).exists()
        else []
    )
    if not json_files:
        print("[ERROR] No JSON files found")
        sys.exit(1)
    missing_json_files = [path for path in json_files if not path.exists()]
    if missing_json_files:
        for json_path in missing_json_files:
            print(f"[ERROR] File not found: {json_path}")
        sys.exit(1)
    results = []
    for json_path in json_files:
        try:
            result = validate_json(
                json_path, all_fields, required_fields, field_categories
            )
        except json.JSONDecodeError as error:
            print(f"[ERROR] Invalid JSON in {json_path}: {error}")
            sys.exit(1)
        results.append(result)
        print_result(result, verbose=not args.quiet)
    line = "=" * 60
    print(f"\n{line}")
    print("Summary")
    print(line)
    passed = sum(1 for result in results if result["valid"])
    average_coverage = (
        sum(result["coverage_rate"] for result in results) / len(results)
        if results
        else 0
    )
    print(f"Validation passed: {passed}/{len(results)}")
    print(f"Average coverage: {average_coverage:.1f}%")
    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
