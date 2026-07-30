#!/usr/bin/env python3
"""Build target-specific APM plugin packages from canonical plugin sources."""

from __future__ import annotations

import argparse
import copy
import os
import re
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode


SCHEMA_VERSION = 1
TEXT_EXTENSIONS = {".json", ".md", ".py", ".txt", ".yaml", ".yml"}
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class BuildError(Exception):
    """Raised for invalid configuration, unsafe input, or build failures."""


@dataclass(frozen=True)
class ArtifactSpec:
    source: PurePosixPath
    destination: PurePosixPath
    frontmatter: bool = False
    frontmatter_glob: str | None = None


@dataclass(frozen=True)
class PackageMetadata:
    version: str
    description: str
    author: str
    license: str
    repository: str


@dataclass(frozen=True)
class TargetSpec:
    name: str
    package_name: str
    frontmatter: Mapping[PurePosixPath, Mapping[str, Any]]
    project_paths: tuple[PurePosixPath, ...]
    global_paths: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class PluginSpec:
    name: str
    root: Path
    package: PackageMetadata
    artifacts: tuple[ArtifactSpec, ...]
    targets: tuple[TargetSpec, ...]


@dataclass(frozen=True)
class GeneratedTree:
    files: Mapping[PurePosixPath, bytes]


@dataclass(frozen=True)
class DriftReport:
    missing: tuple[PurePosixPath, ...]
    changed: tuple[PurePosixPath, ...]
    extra: tuple[PurePosixPath, ...]

    @property
    def clean(self) -> bool:
        return not (self.missing or self.changed or self.extra)

    def format(self, prefix: PurePosixPath = PurePosixPath("packages/plugins")) -> str:
        if self.clean:
            return ""
        lines = ["generated package drift:"]
        for label, paths in (
            ("missing", self.missing),
            ("changed", self.changed),
            ("extra", self.extra),
        ):
            lines.extend(f"  {label:<7} {prefix / path}" for path in paths)
        lines.append("run: make build")
        return "\n".join(lines)


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


# PyYAML follows YAML 1.1. Limit boolean coercion to unambiguous values and
# leave timestamps as strings so configuration types do not depend on spelling.
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


class _QuotedString(str):
    pass


class _DeterministicDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


_DeterministicDumper.add_representer(
    _QuotedString,
    lambda dumper, value: dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"'),
)


def _error(path: Path, location: str, message: str) -> BuildError:
    return BuildError(f"{path}: {location}: {message}")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        documents = list(yaml.load_all(text, Loader=_StrictLoader))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise BuildError(f"{path}: invalid YAML: {exc}") from exc
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise BuildError(f"{path}: YAML must contain exactly one mapping document")
    return documents[0]


def _mapping(value: Any, path: Path, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, location, "must be a mapping")
    return value


def _list(value: Any, path: Path, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(path, location, "must be a list")
    return value


def _string(value: Any, path: Path, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, location, "must be a non-empty string")
    return value


def _keys(mapping: Mapping[str, Any], allowed: set[str], path: Path, location: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise _error(path, location, f"unknown key(s): {', '.join(unknown)}")


def _schema_version(mapping: Mapping[str, Any], path: Path) -> None:
    value = mapping.get("schema_version")
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise _error(path, "schema_version", f"must be integer {SCHEMA_VERSION}")


def _relative_path(
    value: Any,
    path: Path,
    location: str,
    *,
    apm_destination: bool = False,
) -> PurePosixPath:
    raw = _string(value, path, location)
    if "\\" in raw or "\x00" in raw or raw.startswith("/"):
        raise _error(path, location, "must be a safe relative POSIX path")
    candidate = PurePosixPath(raw)
    if candidate == PurePosixPath(".") or any(part in {"", ".", ".."} for part in candidate.parts):
        raise _error(path, location, "must not contain traversal or empty components")
    if candidate.parts and ":" in candidate.parts[0]:
        raise _error(path, location, "must not be drive-qualified")
    if apm_destination and (len(candidate.parts) < 2 or candidate.parts[0] != ".apm"):
        raise _error(path, location, "must be below .apm/")
    return candidate


def _parse_target(path: Path) -> TargetSpec:
    data = _load_yaml_mapping(path)
    _keys(data, {"schema_version", "target", "package_name", "frontmatter", "tests"}, path, "root")
    _schema_version(data, path)
    name = _string(data.get("target"), path, "target")
    if name != path.stem:
        raise _error(path, "target", "must match the target filename")
    package_name = _string(data.get("package_name"), path, "package_name")
    overlays_raw = _mapping(data.get("frontmatter", {}), path, "frontmatter")
    overlays: dict[PurePosixPath, Mapping[str, Any]] = {}
    for raw_source, raw_overlay in overlays_raw.items():
        source = _relative_path(raw_source, path, f"frontmatter.{raw_source}")
        overlay = _mapping(raw_overlay, path, f"frontmatter.{raw_source}")
        overlays[source] = MappingProxyType(dict(overlay))

    tests = _mapping(data.get("tests"), path, "tests")
    _keys(tests, {"project_paths", "global_paths"}, path, "tests")

    def test_paths(key: str) -> tuple[PurePosixPath, ...]:
        values = tuple(
            _relative_path(item, path, f"tests.{key}[{index}]")
            for index, item in enumerate(_list(tests.get(key), path, f"tests.{key}"))
        )
        if len(values) != len(set(values)):
            raise _error(path, f"tests.{key}", "contains duplicate paths")
        return values

    return TargetSpec(
        name=name,
        package_name=package_name,
        frontmatter=MappingProxyType(overlays),
        project_paths=test_paths("project_paths"),
        global_paths=test_paths("global_paths"),
    )


def _parse_plugin(path: Path) -> PluginSpec:
    data = _load_yaml_mapping(path)
    _keys(data, {"schema_version", "package", "artifacts"}, path, "root")
    _schema_version(data, path)
    package = _mapping(data.get("package"), path, "package")
    package_keys = {"version", "description", "author", "license", "repository"}
    _keys(package, package_keys, path, "package")
    missing = sorted(package_keys - set(package))
    if missing:
        raise _error(path, "package", f"missing key(s): {', '.join(missing)}")
    metadata = PackageMetadata(**{key: _string(package[key], path, f"package.{key}") for key in package_keys})
    if not SEMVER_RE.fullmatch(metadata.version):
        raise _error(path, "package.version", "must be a semantic version")

    artifact_values = _list(data.get("artifacts"), path, "artifacts")
    if not artifact_values:
        raise _error(path, "artifacts", "must not be empty")
    artifacts: list[ArtifactSpec] = []
    for index, value in enumerate(artifact_values):
        location = f"artifacts[{index}]"
        artifact = _mapping(value, path, location)
        _keys(artifact, {"source", "destination", "frontmatter", "frontmatter_glob"}, path, location)
        frontmatter = artifact.get("frontmatter", False)
        if not isinstance(frontmatter, bool):
            raise _error(path, f"{location}.frontmatter", "must be a boolean")
        glob = artifact.get("frontmatter_glob")
        if glob is not None:
            glob = _string(glob, path, f"{location}.frontmatter_glob")
            if glob.startswith("/") or "\\" in glob or ".." in PurePosixPath(glob).parts:
                raise _error(path, f"{location}.frontmatter_glob", "must be a safe relative POSIX glob")
        if frontmatter and glob is not None:
            raise _error(path, location, "frontmatter and frontmatter_glob are mutually exclusive")
        artifacts.append(
            ArtifactSpec(
                source=_relative_path(artifact.get("source"), path, f"{location}.source"),
                destination=_relative_path(
                    artifact.get("destination"), path, f"{location}.destination", apm_destination=True
                ),
                frontmatter=frontmatter,
                frontmatter_glob=glob,
            )
        )

    targets_dir = path.parent / "targets"
    if not targets_dir.is_dir() or targets_dir.is_symlink():
        raise BuildError(f"{targets_dir}: targets directory is missing or unsafe")
    target_paths = sorted(targets_dir.glob("*.yml"))
    for target_path in target_paths:
        if target_path.is_symlink():
            raise BuildError(f"{target_path}: symlinked target configuration is not allowed")
    targets = tuple(_parse_target(target) for target in target_paths)
    if not targets:
        raise BuildError(f"{targets_dir}: no target configuration files found")
    names = [target.name for target in targets]
    package_names = [target.package_name for target in targets]
    if len(names) != len(set(names)) or len(package_names) != len(set(package_names)):
        raise BuildError(f"{targets_dir}: target names and package names must be unique")
    return PluginSpec(path.parent.name, path.parent, metadata, tuple(artifacts), targets)


def discover_plugins(repo_root: Path) -> tuple[PluginSpec, ...]:
    plugins_root = repo_root.resolve() / "plugins"
    if not plugins_root.is_dir() or plugins_root.is_symlink():
        raise BuildError(f"{plugins_root}: plugins directory is missing or unsafe")
    config_paths = sorted(plugins_root.glob("*/plugin.yml"), key=lambda item: item.as_posix())
    if not config_paths:
        raise BuildError(f"{plugins_root}: no plugin.yml files found")
    for config_path in config_paths:
        if config_path.is_symlink() or config_path.parent.is_symlink():
            raise BuildError(f"{config_path}: symlinked plugin configuration is not allowed")
    return tuple(_parse_plugin(path) for path in config_paths)


def _safe_source(plugin: PluginSpec, logical: PurePosixPath) -> Path:
    root = plugin.root.resolve()
    current = plugin.root
    for part in logical.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise BuildError(f"{current}: source does not exist: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise BuildError(f"{current}: symlink sources are not allowed")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise BuildError(f"{current}: source escapes plugin directory")
    if not (resolved.is_file() or resolved.is_dir()):
        raise BuildError(f"{current}: source must be a regular file or directory")
    return resolved


def _walk_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.name == "__pycache__" or child.suffix in {".pyc", ".pyo"}:
            continue
        mode = child.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise BuildError(f"{child}: symlink sources are not allowed")
        if stat.S_ISDIR(mode):
            files.extend(_walk_files(child))
        elif stat.S_ISREG(mode):
            files.append(child)
        else:
            raise BuildError(f"{child}: source must be a regular file or directory")
    return tuple(files)


def _normalize_content(path: Path, content: bytes) -> bytes:
    is_text = path.suffix.lower() in TEXT_EXTENSIONS or path.suffix == ""
    if not is_text:
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{path}: text source is not valid UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    return text.encode("utf-8")


def _load_frontmatter(logical: PurePosixPath, content: bytes) -> tuple[dict[str, Any], str]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{logical}: Markdown is not valid UTF-8") from exc
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise BuildError(f"{logical}: expected YAML frontmatter at the first line")
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.rstrip("\r\n") == "---"), None)
    if closing is None:
        raise BuildError(f"{logical}: YAML frontmatter has no closing delimiter")
    raw = "".join(lines[1:closing])
    try:
        documents = list(yaml.load_all(raw, Loader=_StrictLoader))
    except yaml.YAMLError as exc:
        raise BuildError(f"{logical}: invalid YAML frontmatter: {exc}") from exc
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise BuildError(f"{logical}: frontmatter must be exactly one mapping")
    return documents[0], "".join(lines[closing + 1 :])


def _dump_yaml(data: Mapping[str, Any]) -> str:
    return yaml.dump(
        dict(data),
        Dumper=_DeterministicDumper,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
        width=10_000,
    )


def _render_markdown(
    logical: PurePosixPath,
    content: bytes,
    overlay: Mapping[str, Any],
) -> bytes:
    common, body = _load_frontmatter(logical, content)
    merged = dict(common)
    for key, value in overlay.items():
        if value is None:
            if key not in merged:
                raise BuildError(f"{logical}: cannot delete unknown frontmatter field {key!r}")
            del merged[key]
        else:
            merged[key] = value
    rendered = (
        "---\n"
        f"# Generated from {logical}; do not edit.\n"
        f"{_dump_yaml(merged)}"
        "---\n"
        f"{body}"
    )
    return _normalize_content(Path(logical.name), rendered.encode("utf-8"))


def _render_manifest(plugin: PluginSpec, target: TargetSpec, destinations: set[PurePosixPath]) -> bytes:
    includes = sorted(
        {path.as_posix() for path in destinations if len(path.parts) == 2}
        | {
            f"{(PurePosixPath('.apm') / path.parts[1]).as_posix()}/"
            for path in destinations
            if len(path.parts) >= 3
        }
    )
    manifest = {
        "name": target.package_name,
        "version": _QuotedString(plugin.package.version),
        "description": f"{plugin.package.description.rstrip('.')} for {target.name}.",
        "author": plugin.package.author,
        "license": plugin.package.license,
        "dependencies": {"apm": [], "mcp": []},
        "includes": includes,
        "scripts": {},
    }
    return ("# Generated; do not edit.\n" + _dump_yaml(manifest)).encode("utf-8")


def _generate_plugin_target(plugin: PluginSpec, target: TargetSpec) -> dict[PurePosixPath, bytes]:
    generated: dict[PurePosixPath, bytes] = {}
    eligible: dict[PurePosixPath, PurePosixPath] = {}
    for artifact in plugin.artifacts:
        source = _safe_source(plugin, artifact.source)
        if source.is_file():
            if artifact.frontmatter_glob is not None:
                raise BuildError(f"{source}: frontmatter_glob requires a directory source")
            entries = ((source, PurePosixPath(source.name)),)
        else:
            if artifact.frontmatter:
                raise BuildError(f"{source}: frontmatter requires a file source")
            entries = tuple(
                (item, PurePosixPath(item.relative_to(source).as_posix())) for item in _walk_files(source)
            )
        matched_glob = False
        for item, relative in entries:
            destination = artifact.destination if source.is_file() else artifact.destination / relative
            if destination in generated:
                raise BuildError(f"{plugin.root / artifact.source}: duplicate destination {destination}")
            for existing in generated:
                if destination in existing.parents or existing in destination.parents:
                    raise BuildError(f"{plugin.root / artifact.source}: file/directory conflict at {destination}")
            logical = artifact.source if source.is_file() else artifact.source / relative
            content = _normalize_content(item, item.read_bytes())
            is_eligible = artifact.frontmatter or (
                artifact.frontmatter_glob is not None and relative.match(artifact.frontmatter_glob)
            )
            if is_eligible:
                matched_glob = True
                eligible[logical] = destination
                content = _render_markdown(logical, content, target.frontmatter.get(logical, {}))
            generated[destination] = content
        if artifact.frontmatter_glob is not None and not matched_glob:
            raise BuildError(f"{source}: frontmatter_glob {artifact.frontmatter_glob!r} matched no files")

    unknown = sorted(set(target.frontmatter) - set(eligible), key=lambda item: item.as_posix())
    if unknown:
        raise BuildError(f"{plugin.root / 'targets' / (target.name + '.yml')}: overlay source is unknown or ineligible: {unknown[0]}")
    if any(b"@@GENERATOR:" in content for content in generated.values()):
        raise BuildError(f"{plugin.name}/{target.name}: unresolved generator marker")
    generated[PurePosixPath("apm.yml")] = _render_manifest(plugin, target, set(generated))
    return generated


def generate_all(repo_root: Path) -> GeneratedTree:
    files: dict[PurePosixPath, bytes] = {}
    for plugin in discover_plugins(repo_root):
        for target in plugin.targets:
            prefix = PurePosixPath(plugin.name) / target.name
            for relative, content in _generate_plugin_target(plugin, target).items():
                output = prefix / relative
                if output in files:
                    raise BuildError(f"duplicate generated path: {output}")
                files[output] = content
    ordered = {path: files[path] for path in sorted(files, key=lambda item: item.as_posix())}
    return GeneratedTree(MappingProxyType(ordered))


def _scan_output(root: Path) -> dict[PurePosixPath, bytes | None]:
    if not root.exists():
        return {}
    if root.is_symlink() or not root.is_dir():
        return {PurePosixPath("."): None}
    result: dict[PurePosixPath, bytes | None] = {}

    def visit(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.name == "__pycache__" or entry.suffix in {".pyc", ".pyo"}:
                continue
            relative = PurePosixPath(entry.relative_to(root).as_posix())
            mode = entry.lstat().st_mode
            if stat.S_ISDIR(mode):
                visit(entry)
            elif stat.S_ISREG(mode):
                result[relative] = entry.read_bytes()
            else:
                result[relative] = None

    visit(root)
    return result


def check_all(repo_root: Path) -> DriftReport:
    expected = generate_all(repo_root).files
    actual = _scan_output(repo_root.resolve() / "packages" / "plugins")
    expected_paths = set(expected)
    actual_paths = set(actual)
    missing = tuple(sorted(expected_paths - actual_paths, key=lambda item: item.as_posix()))
    extra = tuple(sorted(actual_paths - expected_paths, key=lambda item: item.as_posix()))
    changed = tuple(
        sorted(
            (path for path in expected_paths & actual_paths if actual[path] != expected[path]),
            key=lambda item: item.as_posix(),
        )
    )
    return DriftReport(missing, changed, extra)


def _materialize(root: Path, tree: GeneratedTree) -> None:
    for relative, content in tree.files.items():
        destination = root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        destination.chmod(0o644)
    root.chmod(0o755)
    for directory in (path for path in root.rglob("*") if path.is_dir()):
        directory.chmod(0o755)


def build_all(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    tree = generate_all(repo_root)
    packages = repo_root / "packages"
    if packages.is_symlink() or (packages.exists() and not packages.is_dir()):
        raise BuildError(f"{packages}: packages root must be a real directory")
    packages.mkdir(parents=True, exist_ok=True)
    destination = packages / "plugins"
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise BuildError(f"{destination}: generated output must be a real directory")
    backups = sorted(packages.glob(".plugins.backup-*"))
    if backups:
        raise BuildError(f"{backups[0]}: leftover backup requires manual recovery")
    staging = Path(tempfile.mkdtemp(prefix=".plugins.stage-", dir=packages))
    backup = packages / f".plugins.backup-{uuid.uuid4().hex}"
    moved_old = False
    try:
        _materialize(staging, tree)
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        try:
            os.replace(staging, destination)
        except Exception:
            if moved_old and not destination.exists():
                os.replace(backup, destination)
                moved_old = False
            raise
        if moved_old:
            shutil.rmtree(backup)
    except BuildError:
        raise
    except OSError as exc:
        raise BuildError(f"failed to replace {destination}: {exc}") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report generated package drift without writing")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        if args.check:
            report = check_all(repo_root)
            if not report.clean:
                print(report.format())
                return 1
        else:
            build_all(repo_root)
    except BuildError as exc:
        print(f"build error: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
