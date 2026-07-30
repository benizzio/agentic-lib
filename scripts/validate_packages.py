#!/usr/bin/env python3
"""Audit generated APM packages and enforce repository package invariants."""

from __future__ import annotations

import argparse
import copy
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode


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


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects aliases and duplicate mapping keys."""

    yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            event = self.peek_event()
            raise yaml.constructor.ConstructorError(
                None, None, f"YAML aliases are not allowed: *{event.anchor}", event.start_mark
            )
        return super().compose_node(parent, index)


# Match the builder's YAML semantics: only true/false are booleans and dates remain strings.
for _first, _resolvers in list(_StrictLoader.yaml_implicit_resolvers.items()):
    _StrictLoader.yaml_implicit_resolvers[_first] = [
        item
        for item in _resolvers
        if item[0] not in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
    ]
_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.IGNORECASE), list("tTfF")
)


def _construct_mapping(loader: _StrictLoader, node: MappingNode, deep: bool = False) -> dict[str, Any]:
    if not isinstance(node, MappingNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a mapping", node.start_mark)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                "mapping keys must be strings", key_node.start_mark,
            )
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"duplicate key: {key}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def parse_yaml_mapping(text: str, source: Path | str = "YAML") -> dict[str, Any]:
    try:
        documents = list(yaml.load_all(text, Loader=_StrictLoader))
    except yaml.YAMLError as error:
        raise ValidationError(f"{source}: invalid YAML: {error}") from error
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise ValidationError(f"{source}: YAML must contain exactly one mapping document")
    return documents[0]


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValidationError(f"cannot read {path}: {error}") from error
    return parse_yaml_mapping(text, path)


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
    return raw, parse_yaml_mapping(raw, path)


def discover_packages(repo_root: Path = REPO_ROOT) -> list[Package]:
    plugin_root = repo_root / "plugins"
    generated_root = repo_root / "packages" / "plugins"
    packages: list[Package] = []
    expected_roots: set[Path] = set()
    configs = sorted(plugin_root.glob("*/targets/*.yml"))
    if not configs:
        raise ValidationError(f"no target configurations found under {plugin_root}")
    for config_path in configs:
        config = load_yaml_mapping(config_path)
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
