#!/usr/bin/env python3
"""Audit generated APM packages and enforce repository package invariants."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = REPO_ROOT / "packages" / "plugins"
PLUGIN_ROOT = REPO_ROOT / "plugins"


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class Package:
    plugin: str
    target: str
    root: Path
    config_path: Path
    config: dict[str, Any]


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value in ("null", "Null", "NULL", "~"):
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.startswith(("\"", "'")):
        if value[0] == "\"":
            return json.loads(value)
        if not value.endswith("'"):
            raise ValidationError(f"unterminated quoted scalar: {value}")
        return value[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value == "[]":
        return []
    if value == "{}":
        return {}
    return value


def parse_yaml_subset(text: str, source: Path | str = "YAML") -> dict[str, Any]:
    """Parse the mappings and scalar lists used by target and frontmatter files."""
    rows: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValidationError(f"{source}:{number}: tabs are not valid indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        rows.append((len(raw) - len(raw.lstrip(" ")), raw.lstrip(" ")))

    def block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(rows) or rows[index][0] < indent:
            return {}, index
        is_list = rows[index][1].startswith("- ") or rows[index][1] == "-"
        result: Any = [] if is_list else {}
        while index < len(rows):
            current_indent, content = rows[index]
            if current_indent < indent:
                break
            if current_indent != indent:
                raise ValidationError(
                    f"{source}: unexpected indentation before {content!r}"
                )
            if is_list:
                if not content.startswith("-"):
                    break
                item = content[1:].strip()
                if not item:
                    value, index = block(index + 1, indent + 2)
                    result.append(value)
                else:
                    result.append(_scalar(item))
                    index += 1
                continue
            if content.startswith("-") or ":" not in content:
                raise ValidationError(f"{source}: expected a mapping entry: {content!r}")
            key, raw_value = content.split(":", 1)
            key = str(_scalar(key.strip()))
            if key in result:
                raise ValidationError(f"{source}: duplicate key {key!r}")
            raw_value = raw_value.strip()
            if raw_value:
                result[key] = _scalar(raw_value)
                index += 1
            elif index + 1 < len(rows) and (
                rows[index + 1][0] > indent
                or (rows[index + 1][0] == indent and rows[index + 1][1].startswith("-"))
            ):
                result[key], index = block(index + 1, rows[index + 1][0])
            else:
                result[key] = None
                index += 1
        return result, index

    if not rows:
        return {}
    if rows[0][0] != 0:
        raise ValidationError(f"{source}: top-level content must not be indented")
    parsed, final_index = block(0, 0)
    if final_index != len(rows) or not isinstance(parsed, dict):
        raise ValidationError(f"{source}: top-level value must be a mapping")
    return parsed


def load_yaml_subset(path: Path) -> dict[str, Any]:
    try:
        return parse_yaml_subset(path.read_text(encoding="utf-8"), path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"cannot read {path}: {error}") from error


def frontmatter(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValidationError(f"cannot read {path}: {error}") from error
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError(f"{path}: missing YAML frontmatter")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise ValidationError(f"{path}: unterminated YAML frontmatter") from error
    raw = "\n".join(lines[1:end])
    try:
        raw.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValidationError(f"{path}: frontmatter must be ASCII-compatible") from error
    return raw, parse_yaml_subset(raw, path)


def discover_packages(repo_root: Path = REPO_ROOT) -> list[Package]:
    plugin_root = repo_root / "plugins"
    generated_root = repo_root / "packages" / "plugins"
    packages: list[Package] = []
    expected_roots: set[Path] = set()
    configs = sorted(plugin_root.glob("*/targets/*.yml"))
    if not configs:
        raise ValidationError(f"no target configurations found under {plugin_root}")
    for config_path in configs:
        config = load_yaml_subset(config_path)
        target = config.get("target")
        if not isinstance(target, str) or not target:
            raise ValidationError(f"{config_path}: target must be a non-empty string")
        plugin = config_path.parent.parent.name
        root = generated_root / plugin / target
        expected_roots.add(root.resolve())
        if not (root / "apm.yml").is_file():
            raise ValidationError(
                f"generated package is missing for {plugin}/{target}: {root / 'apm.yml'}"
            )
        packages.append(Package(plugin, target, root, config_path, config))
    actual_roots = {path.parent.resolve() for path in generated_root.glob("*/*/apm.yml")}
    extras = sorted(actual_roots - expected_roots)
    if extras:
        raise ValidationError(
            "generated packages without matching target configs: "
            + ", ".join(str(path) for path in extras)
        )
    return packages


def _run(command: list[str], cwd: Path) -> str | None:
    print(f"+ {shlex.join(command)}  (cwd={cwd})")
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    if completed.returncode:
        return f"command exited with {completed.returncode}: {shlex.join(command)}"
    return None


def _content_checks(package: Package) -> list[str]:
    errors: list[str] = []
    apm_root = package.root / ".apm"
    markdown = sorted(apm_root.rglob("*.md"))
    if not markdown:
        return [f"{package.root}: package contains no generated Markdown"]

    source_modules = {
        path.name
        for path in (REPO_ROOT / "plugins" / package.plugin / "source" / "modules").rglob("*.md")
    }
    agent_root = apm_root / "agents"
    for path in markdown:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n") or text.startswith("---\r\n"):
            try:
                frontmatter(path)
            except ValidationError as error:
                errors.append(str(error))
        if re.search(r"(?:^|[/\\])\.(?:claude|codex)(?:[/\\]|$)", text, re.IGNORECASE):
            errors.append(f"{path}: contains a Claude/Codex absolute-path fragment")
        marker_patterns = (
            r"@@GENERATOR:",
            r"\{\{[^{}]+\}\}",
            r"@@[A-Z][A-Z0-9_]*@@",
            r"__(?:TARGET|PLUGIN|PACKAGE|GENERATOR)[A-Z0-9_]*__",
            r"(?:TODO|FIXME)\s*\(?generator\)?",
        )
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in marker_patterns):
            errors.append(f"{path}: contains an internal generator marker")

    if agent_root.exists():
        for path in agent_root.rglob("*.md"):
            if path.parent != agent_root or path.name in source_modules:
                errors.append(f"{path}: module Markdown must not be under .apm/agents")

    for skill_file in sorted((apm_root / "skills").glob("*/SKILL.md")):
        try:
            _, metadata = frontmatter(skill_file)
        except ValidationError as error:
            errors.append(str(error))
            continue
        if metadata.get("name") != skill_file.parent.name:
            errors.append(
                f"{skill_file}: skill name {metadata.get('name')!r} does not match directory "
                f"{skill_file.parent.name!r}"
            )

    agents = sorted(agent_root.glob("*.md")) if agent_root.exists() else []
    if not agents:
        errors.append(f"{package.root}: package contains no agents")
    for agent in agents:
        try:
            _, metadata = frontmatter(agent)
        except ValidationError as error:
            errors.append(str(error))
            continue
        if package.target == "opencode":
            if metadata.get("mode") != "subagent":
                errors.append(f"{agent}: OpenCode agent mode must be 'subagent'")
            if not isinstance(metadata.get("permission"), dict):
                errors.append(f"{agent}: OpenCode agent permission must be a mapping")
            if "tools" in metadata:
                errors.append(f"{agent}: OpenCode agent must not contain Copilot tools")
        elif package.target == "copilot":
            tools = metadata.get("tools")
            if not isinstance(tools, list) or not tools or not all(
                isinstance(tool, str) for tool in tools
            ):
                errors.append(f"{agent}: Copilot tools must be a non-empty string list")
            forbidden = sorted({"permission", "mode", "temperature"} & metadata.keys())
            if forbidden:
                errors.append(f"{agent}: Copilot agent contains OpenCode fields: {', '.join(forbidden)}")
    return errors


def validate(apm: str, repo_root: Path = REPO_ROOT) -> int:
    global REPO_ROOT
    REPO_ROOT = repo_root
    errors: list[str] = []
    try:
        packages = discover_packages(repo_root)
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for package in packages:
        print(f"Validating {package.plugin}/{package.target}")
        errors.extend(_content_checks(package))
        for path in sorted((package.root / ".apm").rglob("*.md")):
            failure = _run([apm, "audit", "--file", str(path.resolve())], package.root)
            if failure:
                errors.append(failure)
        failure = _run([apm, "pack", "--dry-run", "--verbose"], package.root)
        if failure:
            errors.append(failure)
    if errors:
        print("\nPackage validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(packages)} generated package(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apm", default=os.environ.get("APM", "apm"), help="APM executable")
    args = parser.parse_args()
    return validate(args.apm)


if __name__ == "__main__":
    raise SystemExit(main())
