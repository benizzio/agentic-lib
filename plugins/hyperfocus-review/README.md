# Hyperfocus Review maintenance notes

Experimental. Packaging checks do not establish model behavior or authenticated
tool exposure. The root README's development warning still applies.

## Reviewer-only access

`dry-reviewer` recommends changes; it never implements them. OpenCode denies
edits, shell, unrestricted Code Mode, and subagent delegation. Copilot exposes
no editing, shell/execution, or delegation tool. Both allow native web search
and fetching for documentation, subject to the consuming harness's policies
and availability. Permission does not provision a web-search integration.

OpenCode MCP servers used by this agent must set `codemode: false` so their
individual tools can be called directly. Code Mode is deliberately denied:
although it has no direct filesystem access, it exposes raw HTTP and tools
outside the narrow review workflow. Do not enable it to work around a missing
MCP tool. Verify the tools actually exposed to the installed subagent.

The overlays assume MCP server names `github` and `context7`. Only listed tools
are available; adapt names in the consuming configuration if necessary. Review
writes require OpenCode approval. Tool-level permissions cannot restrict the
method/event arguments of GitHub's review-write tool; inspect each approval.

## Progressive publication references

The agent's operating contract is service-neutral. After identifying a remote
target and publication intent, it loads `review-publication/SKILL.md` and only
the matching service guide under `references/`. Report-only reviews need none
of these references. The GitHub guide includes MCP publication and explicitly
authorized `gh` fallback through the caller, without granting the reviewer a
shell. A fallback never bypasses user authorization or state checks.

Reference skills are packaged alongside the agent, not as standalone agents.
Project installs deploy them under `.agents/skills/`. User-scope installs use
`~/.agents/skills/` with the OpenCode workaround below.

## Installation checks

For project installations, use the package matching your harness:

```sh
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/opencode --target opencode
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/copilot --target copilot
```

Copilot supports adding `--global`. For global OpenCode with APM `0.35.0`,
install shared references and the agent separately, as with Deep Research:

```sh
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/opencode --target agent-skills --global
apm install benizzio/agentic-lib/packages/plugins/hyperfocus-review/opencode/.apm/agents/dry-reviewer.agent.md --target opencode --global
```

Do not install only the agent: remote publication requires the reference bundle.
`make validate` tests isolated project/global installation, reference contents,
permission metadata, and repeat-install idempotence for both targets. See
[`tests/fixtures/hyperfocus-review/README.md`](../../tests/fixtures/hyperfocus-review/README.md)
for model-backed acceptance checks and their verification status.
