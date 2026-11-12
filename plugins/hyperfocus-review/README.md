# Hyperfocus Review maintenance notes

Experimental. Packaging checks do not establish model behavior or authenticated
tool exposure. The root README's development warning still applies.

## Reviewer-only access

`dry-reviewer` recommends changes; it never implements them. It discovers the
tools and execution facilities available in its harness and chooses operations
by their effects, not a fixed exploration-tool list. Tools and shell commands
may inspect code, but must not change reviewed content, source, or versioned
repository artifacts. Normal auxiliary logs, caches, indexes, telemetry files,
and temporary outputs are not violations by themselves. Prefer temporary or
tool-managed locations; dedicated generated-output directories within the
repository are acceptable if protected content is unaffected. Permissions,
privacy requirements, and caller restrictions still apply.
Unfamiliar operations require checking documentation, options, configuration,
hooks, and output paths. If changes to protected content cannot be ruled out,
the agent must ask for clarification or use a safer alternative, not execute
speculatively. Auxiliary writes alone do not require clarification.

### Harness permissions

The OpenCode package requires OpenCode 2.1.4 or later.

- **OpenCode:** direct edits and nested delegation are denied. Code Mode is
  enabled for tool orchestration; MCP servers need not set `codemode: false`.
  Shell commands, unfamiliar tool actions, external directories, and review
  tools are allowed without routine approval by this profile. The broad rule
  also covers newly exposed tools. Later consuming-configuration rules and
  nested tools may impose their own restrictions.
- **Copilot CLI:** the profile includes `execute` for shell commands alongside
  reading, searching, web access, and the existing review integrations. It omits
  editing and delegation tools. Shell approval is controlled by the consuming
  CLI's permission settings, not this profile. Keep interactive approval enabled
  or apply an appropriate host policy; do not assume this profile forces it.
  The profile cannot express all MCP tools except editing tools. Unlisted MCP
  tools need consumer configuration; the agent can discover CLI alternatives
  without the package naming exploration products.

Both targets allow native web search/fetch subject to harness policies and
availability. Permission does not provision tools or a web-search integration.
Existing review/documentation MCP mappings assume server names `github` and
`context7`; adapt them in the consuming configuration if needed. Verify the
tools actually exposed to the installed subagent, not merely its parent.
OpenCode review-write permissions are tool-level and cannot restrict method or
event arguments. The prompt's publication safeguards are cooperative, not
enforced by those permissions. Shell and Code Mode can modify source despite
direct-edit denials; strict protection requires external read-only enforcement.

## Publication discovery

The agent discovers the remote version-control review service, live tool schemas,
documentation, and permitted capabilities before publication. GitHub PR review
comments are an example, not a prescribed API workflow or a promise of other
service support. This package ships only the agent, with no publication skill.
Discovery cannot provision tools: retain/adapt the explicit MCP mappings above,
and configure unlisted Copilot MCP tools in the consuming profile.

Report-only requests cause no publication writes. Publication requires confirmed
target/intent, identity and duplicate checks, consistent reviewed base/head and
comparison before publication and submission, and safe invocation-owned review
ID binding for later mutations. Existing pending state stops publication. An
operation selecting only the current user's pending review is not safe ID binding.
Use only an explicitly authorized equivalent operation or return the full report.
Alternative transports require explicit authorization separate from permission
to run a command; never search for credentials or silently switch transports.

Findings are added sequentially at valid anchors; unanchorable findings go in the
summary. Partial or ambiguous failures require state inspection and an accurate
recovery report, not blind retries or incomplete submission. Success requires
verified submission. These are cooperative reviewer policies, not a sandbox;
strict source-write protection requires external read-only source enforcement.

## Installation checks

Use APM `0.35.0`, the version pinned by this repository's validation suite.
This is separate from the OpenCode minimum version above.

For project installations, use the package matching your harness:

```sh
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/opencode --target opencode
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/copilot --target copilot
```

Both targets support adding `--global`. For example:

```sh
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/opencode --target opencode --global
```

No shared-skill or two-step install is required for Hyperfocus Review. Deep
Research's shared-skill workaround remains separate. `make validate` tests
isolated project/global installation, exact agent contents,
permission metadata, and repeat-install idempotence for both targets. See
[`tests/fixtures/hyperfocus-review/README.md`](../../tests/fixtures/hyperfocus-review/README.md)
for model-backed acceptance checks and their verification status.
