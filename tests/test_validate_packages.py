from __future__ import annotations

import copy
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

    def test_requires_ordered_json_edit_rules_for_deep_research_opencode(self) -> None:
        package = validate_packages.Package(
            plugin="deep-research",
            target="opencode",
            root=Path("/package"),
            config_path=Path("/target.yml"),
            config={},
        )
        agent = Path("/package/.apm/agents/web-search.agent.md")
        valid = {
            "name": "web-search-agent",
            "permission": {
                "edit": {"*": "deny", "*.json": "allow"},
                "bash": {"*": "deny", "date *": "allow"},
            },
        }

        self.assertEqual(
            validate_packages.agent_capability_errors(package, agent, valid), []
        )

        invalid = {
            **valid,
            "permission": {
                **valid["permission"],
                "edit": {"*.json": "allow", "*": "deny"},
            },
        }
        self.assertIn(
            f"{agent}: OpenCode web-search agent must deny edits by default and allow *.json",
            validate_packages.agent_capability_errors(package, agent, invalid),
        )

    def test_requires_edit_without_execute_for_deep_research_copilot(self) -> None:
        package = validate_packages.Package(
            plugin="deep-research",
            target="copilot",
            root=Path("/package"),
            config_path=Path("/target.yml"),
            config={},
        )
        agent = Path("/package/.apm/agents/web-search.agent.md")

        self.assertEqual(
            validate_packages.agent_capability_errors(
                package,
                agent,
                {
                    "name": "web-search-agent",
                    "tools": ["read", "edit", "search", "web"],
                },
            ),
            [],
        )
        self.assertEqual(
            validate_packages.agent_capability_errors(
                package,
                agent,
                {
                    "name": "web-search-agent",
                    "tools": ["read", "edit", "search", "web", "execute"],
                },
            ),
            [
                f"{agent}: Copilot web-search agent tools must be "
                "['read', 'edit', 'search', 'web']"
            ],
        )


class DryReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packages = {
            package.target: package
            for package in validate_packages.discover_packages()
            if package.plugin == "hyperfocus-review"
        }

    def check_metadata(self, target: str, metadata: dict) -> list[str]:
        return validate_packages.agent_frontmatter_errors(
            self.packages[target], Path("dry-reviewer.agent.md"), metadata
        )

    def metadata(self, target: str) -> dict:
        return validate_packages.frontmatter(
            self.packages[target].root / ".apm/agents/dry-reviewer.agent.md"
        )[1]

    def test_generated_packages_pass_content_checks(self) -> None:
        self.assertEqual(set(self.packages), {"opencode", "copilot"})
        for package in self.packages.values():
            self.assertEqual(validate_packages._content_checks(package, ROOT), [])

    def test_canonical_body_and_package_version_are_preserved(self) -> None:
        source = ROOT / "plugins/hyperfocus-review/source/agents/dry-reviewer.md"
        source_body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
        source_version = validate_packages.load_yaml_mapping(
            ROOT / "plugins/hyperfocus-review/plugin.yml"
        )["package"]["version"]
        self.assertEqual(source_version, "0.1.4")
        for target, package in self.packages.items():
            manifest = validate_packages.load_yaml_mapping(package.root / "apm.yml")
            self.assertEqual(manifest["name"], f"hyperfocus-review-{target}")
            self.assertEqual(manifest["version"], source_version)
            self.assertEqual(manifest["includes"], [".apm/agents/"])
            agent = package.root / ".apm/agents/dry-reviewer.agent.md"
            body = agent.read_text(encoding="utf-8").split("---", 2)[2].strip()
            self.assertEqual(body, source_body)

    def test_review_scope_contract_supports_confirmed_whole_codebase(self) -> None:
        # These are static prompt regressions, not evidence of model behavior.
        source = ROOT / "plugins/hyperfocus-review/source/agents/dry-reviewer.md"
        paths = [source] + [
            package.root / ".apm/agents/dry-reviewer.agent.md"
            for package in self.packages.values()
        ]
        required_rules = (
            "For changed-code reviews, expect a PR/MR reference",
            "For a confirmed whole-codebase review, identify the repository and "
            "reviewed revision; no base or diff is required.",
            "By default, review changed code only.",
            "context gathering, not permission to review it.",
            "Review the whole codebase only after the explicit request and confirmation below.",
            "A whole-codebase review is an exceptional process and requires an explicit "
            "request AND confirmation after explaining that its size may exceed context "
            "capacity and reduce review quality.",
            "Stop before reviewing until confirmed.",
            "If questions are unavailable, return the clarification request to the caller "
            "instead of assuming consent.",
            "Batch large review scopes by coherent responsibility.",
            "Compare code within the review scope with relevant surrounding behavior.",
            "File within the review scope and precise line/range at the reviewed revision.",
            "For a changed-code review, use a changed file.",
            "reviewed revision (base/head and comparison for changed-code reviews)",
        )
        for path in paths:
            with self.subTest(path=path):
                text = " ".join(path.read_text(encoding="utf-8").split())
                description = validate_packages.frontmatter(path)[1]["description"]
                self.assertIn("Review changed code by default", description)
                self.assertIn("whole codebase after explicit request and confirmation", description)
                for rule in required_rules:
                    self.assertIn(rule, text)
                self.assertNotIn("- Review changed code only.", text)
                self.assertNotIn("- Changed file and precise line/range", text)

    def test_auxiliary_writes_do_not_override_source_protection(self) -> None:
        source = ROOT / "plugins/hyperfocus-review/source/agents/dry-reviewer.md"
        body = " ".join(source.read_text(encoding="utf-8").split())
        for rule in (
            "Read-only protects the content being inspected or reviewed, not every filesystem side effect of a tool.",
            "Do not reject an otherwise permitted operation solely because it produces them.",
            "directories within the repository are acceptable when they do not alter reviewed content or other repository source artifacts.",
            "Respect applicable permissions, privacy requirements, and caller restrictions.",
            "Do not modify source, tests, manifests, lockfiles, configuration, or other versioned repository artifacts",
            "Do not ask for clarification merely because an operation writes auxiliary data.",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, body)

    def test_utility_contract_requires_domain_independent_usefulness(self) -> None:
        # Static prompt regressions only; these do not exercise model decisions.
        source = ROOT / "plugins/hyperfocus-review/source/agents/dry-reviewer.md"
        paths = [source] + [
            package.root / ".apm/agents/dry-reviewer.agent.md"
            for package in self.packages.values()
        ]
        required_rules = (
            "Utility code is functionality generic enough for use outside its current "
            "source unit, unrelated to any application domain, and useful for multiple "
            "modules or packages of the application.",
            "Confirm that status before proposing extraction",
            "**Language utility:** basic/generic operations extending language or type facilities",
            "**Infrastructure utility:** operations generic within the adopted stack",
            "Single use alone neither proves nor rules out utility status; require a "
            "demonstrably generic responsibility and a useful boundary, not imagined future consumers.",
            "Respect intentional wrappers, domain adapters, and layer separation.",
            "## 4. Check repeated non-utility behavior and simplify",
            "Recommend consolidation only for the same responsibility when behavior is "
            "preserved and the abstraction is simpler than duplication.",
            "Reject suggestions that introduce coupling, cycles, speculative generality, "
            "or obscure distinct domain rules.",
            "Similar syntax is not evidence of interchangeable behavior.",
            "Relevant compatibility considerations and why behavior is preserved.",
        )
        for path in paths:
            with self.subTest(path=path):
                text = " ".join(path.read_text(encoding="utf-8").split())
                for rule in required_rules:
                    self.assertIn(rule, text)

    def test_publication_discovers_live_capabilities_without_bundled_skill(self) -> None:
        # Static prompt regressions only. Canonical parity is checked separately.
        source_root = ROOT / "plugins/hyperfocus-review/source"
        body = " ".join((source_root / "agents/dry-reviewer.md").read_text(encoding="utf-8").split())
        for rule in (
            "## 6. Publish review when available and permitted; otherwise report",
            "Discover the remote version-control review service",
            "live tool schemas and current documentation",
            "capabilities, selection semantics, and side effects",
            "If schemas, documentation, capabilities, or permissions needed for safe publication are unavailable, return the complete report",
            "Honor report-only requests with no publication writes",
            "both base and head AND comparison consistency",
            "Repeat this check before submission.",
            "If pending state from outside this invocation is found, stop publication and report it.",
            "provably target the invocation-owned review by its recorded identifier",
            "Current-user pending-review selection is not safe ID binding",
            "use only an explicitly authorized equivalent operation or stop with the full report",
            "Put unanchorable findings, including whole-codebase or unchanged locations outside the diff, in the review summary",
            "Do not approve, request changes, resolve threads, merge, or delete review state.",
            "Do not blindly retry, switch transports, or silently submit an incomplete review.",
            "Confirm submission from service evidence before claiming success.",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, body)
        for obsolete in ("review-publication", "pull_request_review_write", "submit_pending", "COMMENT"):
            self.assertNotIn(obsolete, body)
        self.assertEqual(list((source_root / "skills").rglob("*.md")), [])
        for package in self.packages.values():
            self.assertFalse((package.root / ".apm/skills").exists())
            for scope in ("project", "global"):
                self.assertEqual(len(package.config["tests"][f"{scope}_paths"]), 1)
        self.assertFalse(any(rule["action"] == "skill" for rule in self.metadata("opencode")["permissions"]))

    def test_web_access_and_direct_edit_restrictions(self) -> None:
        rules = self.metadata("opencode")["permissions"]
        for action in ("websearch", "webfetch"):
            self.assertIn({"action": action, "resource": "*", "effect": "allow"}, rules)
        for action in ("edit", "subagent"):
            self.assertIn({"action": action, "resource": "*", "effect": "deny"}, rules)
            for effect in ("ask", "allow"):
                modified = [
                    {**rule, "effect": effect} if rule["action"] == action else rule
                    for rule in rules
                ]
                self.assertTrue(self.check_metadata("opencode", {**self.metadata("opencode"), "permissions": modified}))
        tools = self.metadata("copilot")["tools"]
        self.assertIn("web", tools)
        self.assertIn("execute", tools)
        self.assertFalse({"edit", "agent"} & set(tools))
        for tool in ("edit", "agent"):
            self.assertTrue(self.check_metadata("copilot", {**self.metadata("copilot"), "tools": tools + [tool]}))

    def test_execution_and_tool_discovery_require_appropriate_permissions(self) -> None:
        metadata = self.metadata("opencode")
        rules = metadata["permissions"]
        self.assertEqual(rules[0], {"action": "*", "resource": "*", "effect": "ask"})
        self.assertIn({"action": "execute", "resource": "*", "effect": "allow"}, rules)
        self.assertIn({"action": "shell", "resource": "*", "effect": "ask"}, rules)
        self.assertFalse(any(
            "*" in rule["action"] and rule["effect"] == "allow"
            for rule in rules
        ))
        for action, effect in (("*", "allow"), ("*", "deny"), ("shell", "allow"), ("shell", "deny"), ("execute", "deny")):
            with self.subTest(action=action, effect=effect):
                modified = [
                    {**rule, "effect": effect} if rule["action"] == action else rule
                    for rule in rules
                ]
                self.assertTrue(self.check_metadata("opencode", {**metadata, "permissions": modified}))

    def test_behavioral_fixtures_have_distinct_cases_and_expectations(self) -> None:
        fixtures = validate_packages.load_yaml_mapping(
            ROOT / "tests/fixtures/hyperfocus-review/cases.yaml"
        )["cases"]
        self.assertEqual(len(fixtures), 30)
        self.assertEqual(len({case["id"] for case in fixtures}), 30)
        for case in fixtures:
            with self.subTest(case=case["id"]):
                for field in ("id", "request", "expected"):
                    self.assertIsInstance(case[field], str)
                    self.assertTrue(case[field].strip())
                if "files" in case:
                    self.assertIsInstance(case["files"], dict)
                    if case.get("review_scope") == "whole-codebase":
                        self.assertTrue(case["revision"].strip())
                        self.assertNotIn("diff", case)
                    else:
                        self.assertTrue(case["diff"].strip())
                    self.assertTrue(all(isinstance(value, str) for value in case["files"].values()))

    def test_publication_fixtures_cover_discovery_and_recovery_decisions(self) -> None:
        # Expected decisions, not an execution of the publication contract.
        fixtures = {
            case["id"]: case
            for case in validate_packages.load_yaml_mapping(
                ROOT / "tests/fixtures/hyperfocus-review/cases.yaml"
            )["cases"]
        }
        self.assertNotIn("progressive-service-reference", fixtures)
        for case_id, decision in (
            ("discovery-based-publication", "no publication writes or installed-guide dependency"),
            ("synthetic-service-publication", "Discover ForgeBox capabilities"),
            ("publication-missing-contract", "missing capability/schema/documentation/permission"),
            ("existing-pending-review", "current-user identity does not prove invocation ownership"),
            ("review-id-selection-ambiguity", "do not create a review"),
            ("stale-publication-comparison", "reviewed base/head AND comparison consistency at both gates"),
            ("publication-anchor-recovery", "never invent anchors"),
            ("authorized-cli-execution", "request it separately from shell approval"),
        ):
            with self.subTest(case=case_id):
                self.assertIn(decision, fixtures[case_id]["expected"])

    def test_scope_fixtures_cover_confirmation_and_unchanged_evidence(self) -> None:
        fixtures = {
            case["id"]: case
            for case in validate_packages.load_yaml_mapping(
                ROOT / "tests/fixtures/hyperfocus-review/cases.yaml"
            )["cases"]
        }
        unconfirmed = fixtures["whole-codebase-confirmation"]
        self.assertNotIn("prior_messages", unconfirmed)
        self.assertIn("do not start whole-codebase review before confirmation", unconfirmed["expected"])
        confirmed = fixtures["whole-codebase-confirmed-no-diff"]
        self.assertEqual([message["role"] for message in confirmed["prior_messages"]], ["user", "assistant"])
        self.assertIn("entire repository", confirmed["prior_messages"][0]["content"])
        self.assertIn("context capacity and reduce review quality", confirmed["prior_messages"][1]["content"])
        self.assertTrue(confirmed["request"].startswith("Confirmed."))
        self.assertIn("unchanged app.py lines 1-2", confirmed["expected"])
        self.assertEqual(confirmed["files"]["app.py"], "def label_key(value):\n    return value.strip().casefold()\n")
        boundary = fixtures["changed-code-scope-boundary"]
        self.assertIn("unrelated.py", boundary["files"])
        self.assertNotIn("unrelated.py", boundary["diff"])
        self.assertIn("do not report unrelated unchanged unrelated.py", boundary["expected"])

    def test_utility_fixtures_distinguish_generic_operations_from_domain_policy(self) -> None:
        fixtures = {
            case["id"]: case
            for case in validate_packages.load_yaml_mapping(
                ROOT / "tests/fixtures/hyperfocus-review/cases.yaml"
            )["cases"]
        }
        for case_id, location, consumers, compatibility in (
            ("language-extraction", "shared/sequences.py", "package_a and package_b", "list and empty-input behavior"),
            ("infrastructure-extraction", "infrastructure/events.py", "orders and billing modules", "event-schema compatibility"),
        ):
            with self.subTest(case=case_id):
                expected = fixtures[case_id]["expected"]
                self.assertIn("unrelated to any application domain", expected)
                self.assertIn("demonstrably useful across", expected)
                for evidence in (location, consumers, compatibility):
                    self.assertIn(evidence, expected)
        domain = fixtures["domain-repetition"]["expected"]
        for rule in (
            "Repeated domain behavior under section 4",
            "preserved active, balance, and suspended checks",
            "not a language or infrastructure utility",
            "even though it repeats and could be called outside this source unit",
            "Keep the abstraction within the membership domain",
        ):
            self.assertIn(rule, domain)

    def test_rejects_policy_broadening_reordering_and_missing_rules(self) -> None:
        metadata = self.metadata("opencode")
        rules = metadata["permissions"]
        mutations = [
            rules[1:],
            list(reversed(rules)),
            rules + [{"action": "edit", "resource": "*", "effect": "allow"}],
            [{**rule, "effect": "allow"} if rule["action"] == "shell" else rule for rule in rules],
            [{**rule, "effect": "allow"} if rule["action"] == "github_pull_request_review_write" else rule for rule in rules],
            [{**rule, "extra": True} for rule in rules],
            {},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertTrue(self.check_metadata("opencode", {**metadata, "permissions": mutation}))

    def test_rejects_cross_target_fields_models_and_identity_bypass(self) -> None:
        for target, changes in (
            ("opencode", {"tools": ["read"]}),
            ("opencode", {"include-custom-instructions": True}),
            ("opencode", {"permission": {}}),
            ("copilot", {"permissions": []}),
            ("copilot", {"mode": "subagent"}),
            ("copilot", {"include-custom-instructions": False}),
            ("copilot", {"tools": ["*"]}),
            ("copilot", {"tools": ["read", "search", "execute"]}),
            ("opencode", {"model": "pinned"}),
            ("copilot", {"model": "pinned"}),
            ("opencode", {"name": "other-agent"}),
            ("copilot", {"name": "other-agent"}),
        ):
            with self.subTest(target=target, changes=changes):
                metadata = copy.deepcopy(self.metadata(target))
                metadata.update(changes)
                self.assertTrue(self.check_metadata(target, metadata))


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
