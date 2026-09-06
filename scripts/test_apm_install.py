#!/usr/bin/env python3
"""Exercise APM packages through real project and global installs."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_packages import (
    Package,
    REPO_ROOT,
    ValidationError,
    agent_capability_errors,
    discover_packages,
    frontmatter,
    load_yaml_mapping,
)


REQUIRED_APM_VERSION = "0.29.1"
GLOBAL_INSTRUCTION = (
    REPO_ROOT / ".apm" / "instructions" / "global-AGENTS.instructions.md"
)
DEEP_RESEARCH_SKILLS = {
    "research",
    "research-add-fields",
    "research-add-items",
    "research-deep",
    "research-report",
}
DEEP_RESEARCH_MODULES = {
    "academic-papers.md",
    "chinese-tech.md",
    "general-web.md",
    "github-debug.md",
    "stackoverflow.md",
}
TARGET_LAYOUTS = {
    "opencode": {
        "project_agents": Path(".opencode/agents"),
        "global_agents": Path(".config/opencode/agents"),
        "other_project": Path(".github/agents"),
        "other_global": Path(".copilot/agents"),
        "project_skills": Path(".agents/skills"),
        "global_skills": Path(".config/opencode/skills"),
        "rename_agent": True,
    },
    "copilot": {
        "project_agents": Path(".github/agents"),
        "global_agents": Path(".copilot/agents"),
        "other_project": Path(".opencode/agents"),
        "other_global": Path(".config/opencode/agents"),
        "project_skills": Path(".agents/skills"),
        "global_skills": Path(".agents/skills"),
        "rename_agent": False,
    },
}


def run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    print(f"+ {shlex.join(command)}  (cwd={cwd})")
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return completed


def require_success(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    completed = run(command, cwd, env)
    if completed.returncode:
        raise ValidationError(
            f"command exited with {completed.returncode}: {shlex.join(command)}"
        )


def check_apm_version(apm: str) -> None:
    completed = subprocess.run([apm, "--version"], text=True, capture_output=True)
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    versions = re.findall(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", output)
    if completed.returncode or versions != [REQUIRED_APM_VERSION]:
        raise ValidationError(
            f"APM version must be exactly {REQUIRED_APM_VERSION}; got {output or 'no output'}"
        )


def configured_paths(package: Package, scope: str) -> list[Path]:
    tests = package.config.get("tests")
    values = tests.get(f"{scope}_paths") if isinstance(tests, dict) else None
    if not isinstance(values, list) or not values or not all(isinstance(item, str) for item in values):
        raise ValidationError(
            f"{package.config_path}: tests.{scope}_paths must be a non-empty string list"
        )
    paths = [Path(item) for item in values]
    if any(path.is_absolute() or ".." in path.parts for path in paths):
        raise ValidationError(f"{package.config_path}: install assertion paths must be relative")
    return paths


def expected_paths(package: Package, scope: str) -> set[Path]:
    configured = set(configured_paths(package, scope))
    layout = TARGET_LAYOUTS.get(package.target)
    if layout is None:
        raise ValidationError(f"unsupported APM install target for path assertions: {package.target}")
    skill_root = layout[f"{scope}_skills"]
    skill_files = sorted((package.root / ".apm" / "skills").glob("**/*"))
    configured.update(
        skill_root / path.relative_to(package.root / ".apm" / "skills")
        for path in skill_files
        if path.is_file()
    )
    agent_root = layout[f"{scope}_agents"]
    for source in sorted((package.root / ".apm" / "agents").glob("*.md")):
        name = source.name
        if layout["rename_agent"] and name.endswith(".agent.md"):
            name = name[: -len(".agent.md")] + ".md"
        configured.add(agent_root / name)
    return configured


def assert_frontmatter(package: Package, agent: Path) -> None:
    _, metadata = frontmatter(agent)
    if package.target == "opencode":
        if metadata.get("mode") != "subagent" or not isinstance(metadata.get("permission"), dict):
            raise ValidationError(f"{agent}: installed OpenCode frontmatter is incompatible")
        if "tools" in metadata:
            raise ValidationError(f"{agent}: installed OpenCode agent contains Copilot tools")
    elif package.target == "copilot":
        tools = metadata.get("tools")
        if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
            raise ValidationError(f"{agent}: installed Copilot tools are not a string list")
        if {"mode", "permission", "temperature"} & metadata.keys():
            raise ValidationError(f"{agent}: installed Copilot agent contains OpenCode fields")
    capability_errors = agent_capability_errors(package, agent, metadata)
    if capability_errors:
        raise ValidationError("; ".join(capability_errors))


def assert_install(package: Package, root: Path, scope: str) -> None:
    missing = sorted(path for path in expected_paths(package, scope) if not (root / path).is_file())
    if missing:
        raise ValidationError(
            f"{package.plugin}/{package.target} {scope} install is missing: "
            + ", ".join(str(path) for path in missing)
        )
    layout = TARGET_LAYOUTS[package.target]
    agent_root = root / layout[f"{scope}_agents"]
    agents = sorted(agent_root.glob("*.md")) if agent_root.exists() else []
    expected_agent_count = len(list((package.root / ".apm" / "agents").glob("*.md")))
    if len(agents) != expected_agent_count:
        raise ValidationError(
            f"{agent_root}: expected {expected_agent_count} agents, found {len(agents)}"
        )
    web_search_agents = [path for path in agents if path.name.startswith("web-search")]
    if len(web_search_agents) != 1:
        raise ValidationError(f"{agent_root}: expected exactly one web-search agent")
    for agent in agents:
        assert_frontmatter(package, agent)
    other = root / layout[f"other_{scope}"]
    if other.exists():
        raise ValidationError(f"{other}: other target's agent directory was created")
    standalone_modules = set(
        path.name
        for path in (REPO_ROOT / "plugins" / package.plugin / "source" / "modules").rglob("*.md")
    )
    if standalone_modules & {path.name for path in agents}:
        raise ValidationError(f"{agent_root}: modules were installed as standalone agents")
    if package.plugin == "deep-research":
        skills_root = root / layout[f"{scope}_skills"]
        installed_skills = {
            path.parent.name for path in skills_root.glob("*/SKILL.md")
        }
        if installed_skills != DEEP_RESEARCH_SKILLS:
            raise ValidationError(
                f"{skills_root}: expected skills {sorted(DEEP_RESEARCH_SKILLS)}, "
                f"found {sorted(installed_skills)}"
            )
        research = skills_root / "research"
        modules = research / "references" / "web-search-modules"
        installed_modules = {path.name for path in modules.glob("*.md")}
        if installed_modules != DEEP_RESEARCH_MODULES:
            raise ValidationError(
                f"{modules}: expected modules {sorted(DEEP_RESEARCH_MODULES)}, "
                f"found {sorted(installed_modules)}"
            )
        for required in (
            research / "validate_json.py",
            research / "requirements.txt",
            research / "references" / "UPSTREAM_LICENSE",
        ):
            if not required.is_file():
                raise ValidationError(f"{required}: required Deep Research resource is missing")


def run_validator_regressions(skills_root: Path, cwd: Path, env: dict[str, str]) -> None:
    validators = sorted(skills_root.glob("*/validate_json.py"))
    if not validators or any(
        not (validator.parent / "requirements.txt").is_file() for validator in validators
    ):
        raise ValidationError(f"{skills_root}: installed validator or requirements.txt is missing")
    fixture_dir = cwd / "validator-fixtures"
    fixture_dir.mkdir()
    fields = fixture_dir / "fields.yaml"
    complete = fixture_dir / "complete.json"
    missing = fixture_dir / "missing.json"
    malformed = fixture_dir / "empty-fields.yaml"
    fields.write_text(
        "fields:\n"
        "  identity:\n"
        "    - name: title\n"
        "      required: true\n"
        "    - name: note\n"
        "      required: false\n",
        encoding="utf-8",
    )
    complete.write_text('{"identity": {"title": "present"}}\n', encoding="utf-8")
    missing.write_text('{"identity": {"note": "optional"}}\n', encoding="utf-8")
    malformed.write_text("fields: []\n", encoding="utf-8")
    for validator in validators:
        require_success(
            [sys.executable, str(validator), "--fields", str(fields), "--json", str(complete), "--quiet"],
            cwd,
            env,
        )
        for invalid_fields, result in ((fields, missing), (malformed, complete)):
            completed = run(
                [
                    sys.executable,
                    str(validator),
                    "--fields",
                    str(invalid_fields),
                    "--json",
                    str(result),
                    "--quiet",
                ],
                cwd,
                env,
            )
            if completed.returncode == 0:
                raise ValidationError(f"{validator}: invalid regression fixture unexpectedly passed")


def temp_parent(repo_root: Path) -> Path:
    candidates = [Path("/tmp"), Path(tempfile.gettempdir()).resolve()]
    for candidate in candidates:
        if candidate.is_dir() and not candidate.resolve().is_relative_to(repo_root.resolve()):
            return candidate
    raise ValidationError("no temporary directory outside the repository is available")


def test_package(apm: str, package: Package, parent: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=f"apm-{package.plugin}-{package.target}-", dir=parent) as raw:
        temp = Path(raw)
        project = temp / "project"
        project_home = temp / "project-home"
        global_work = temp / "global-consumer"
        global_home = temp / "global-home"
        for path in (project, project_home, global_work, global_home):
            path.mkdir()
        package_path = str(package.root.resolve())

        project_env = os.environ.copy()
        project_env["HOME"] = str(project_home)
        require_success(
            [apm, "install", package_path, "--target", package.target], project, project_env
        )
        require_success([apm, "audit", "--ci"], project, project_env)
        assert_install(package, project, "project")
        project_skills = project / TARGET_LAYOUTS[package.target]["project_skills"]
        run_validator_regressions(project_skills, project, project_env)

        global_env = os.environ.copy()
        global_env["HOME"] = str(global_home)
        require_success(
            [apm, "install", package_path, "--target", package.target, "--global"],
            global_work,
            global_env,
        )
        global_manifest_root = global_home / ".apm"
        if not global_manifest_root.is_dir():
            raise ValidationError(f"{global_manifest_root}: global APM state was not created")
        for name in ("apm.yml", "apm.lock.yaml"):
            state_file = global_manifest_root / name
            if not state_file.is_file():
                raise ValidationError(f"{state_file}: global APM state file is missing")
        # APM has no audit --global mode. Verify its user-scope state and actual
        # deployment destinations directly instead of project-auditing symlinks.
        assert_install(package, global_home, "global")
        global_skills = global_home / TARGET_LAYOUTS[package.target]["global_skills"]
        run_validator_regressions(global_skills, global_work, global_env)


def global_instruction_body() -> str:
    text = GLOBAL_INSTRUCTION.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError(f"{GLOBAL_INSTRUCTION}: missing YAML frontmatter")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise ValidationError(f"{GLOBAL_INSTRUCTION}: unterminated YAML frontmatter") from error
    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise ValidationError(f"{GLOBAL_INSTRUCTION}: instruction body is empty")
    return body


def test_root_global_instruction(apm: str, parent: Path) -> None:
    _, metadata = frontmatter(GLOBAL_INSTRUCTION)
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        raise ValidationError(f"{GLOBAL_INSTRUCTION}: description must be a non-empty string")
    if "applyTo" in metadata:
        raise ValidationError(f"{GLOBAL_INSTRUCTION}: global instruction must not declare applyTo")

    with tempfile.TemporaryDirectory(prefix="apm-root-opencode-global-", dir=parent) as raw:
        temp = Path(raw)
        work = temp / "consumer"
        home = temp / "home"
        package = temp / "package"
        work.mkdir()
        home.mkdir()
        package.mkdir()
        shutil.copy2(REPO_ROOT / "apm.yml", package / "apm.yml")
        shutil.copytree(
            REPO_ROOT / ".apm" / "instructions", package / ".apm" / "instructions"
        )
        shutil.copytree(REPO_ROOT / ".apm" / "skills", package / ".apm" / "skills")
        env = os.environ.copy()
        env["HOME"] = str(home)

        require_success(
            [apm, "install", str(package), "--target", "opencode", "--global"],
            work,
            env,
        )
        manifest = load_yaml_mapping(home / ".apm" / "apm.yml")
        declared_targets = manifest.get("targets", manifest.get("target"))
        if declared_targets != ["opencode"]:
            raise ValidationError(
                f"{home / '.apm' / 'apm.yml'}: expected targets: [opencode], "
                f"found {declared_targets!r}"
            )

        require_success([apm, "compile", "--global", "--dry-run"], work, env)
        output = home / ".config" / "opencode" / "AGENTS.md"
        if output.exists():
            raise ValidationError(f"{output}: global compile dry-run wrote an output file")
        if (home / ".claude" / "CLAUDE.md").exists():
            raise ValidationError("OpenCode-only global compile created a Claude context file")

        require_success([apm, "compile", "--global"], work, env)
        if not output.is_file():
            raise ValidationError(f"{output}: compiled OpenCode global instructions are missing")
        compiled = output.read_text(encoding="utf-8")
        if "Generated by APM CLI" not in compiled or global_instruction_body() not in compiled:
            raise ValidationError(f"{output}: compiled content does not contain the packaged instruction")
        if (home / ".claude" / "CLAUDE.md").exists():
            raise ValidationError("OpenCode-only global compile created a Claude context file")

        before = output.read_bytes()
        require_success([apm, "compile", "--global"], work, env)
        if output.read_bytes() != before:
            raise ValidationError(f"{output}: repeated global compilation was not idempotent")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apm", default=os.environ.get("APM", "apm"), help="APM executable")
    args = parser.parse_args()
    try:
        check_apm_version(args.apm)
        packages = discover_packages()
        parent = temp_parent(REPO_ROOT)
        for package in packages:
            print(f"Testing APM installs for {package.plugin}/{package.target}")
            test_package(args.apm, package, parent)
        print("Testing root package OpenCode global instructions")
        test_root_global_instruction(args.apm, parent)
    except (OSError, ValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Tested project and global installs for {len(packages)} generated package(s) and root.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
