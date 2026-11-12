# Hyperfocus Review maintenance notes

Experimental. Packaging checks do not establish model behavior or authenticated
tool exposure. The root README's development warning still applies.

## Reviewer-only access

`dry-reviewer` recommends changes; it never implements them. It discovers the
tools and execution facilities available in its harness and chooses operations
by their effects, not a fixed exploration-tool list. Tools and shell commands
may inspect code, but must not change source or versioned repository artifacts.
Unfamiliar operations require checking documentation, options, configuration,
hooks, and output paths. If source-write effects cannot be ruled out, the agent
must ask for clarification or use a safer alternative, not execute speculatively.
Caches, indexes, and temporary outputs are allowed outside the source tree when
their locations and effects are understood and permitted by the caller.

### Harness permissions

The OpenCode package requires OpenCode 2.1.4 or later.

- **OpenCode:** direct edits and nested delegation are denied. Code Mode is
  enabled for tool orchestration; MCP servers need not set `codemode: false`.
  Shell commands and unfamiliar tool actions require approval, rather than a
  hardcoded command/tool allowlist. Existing read-only documentation and review
  inspection integrations remain allowed. Nested tools retain their permissions.
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
Review-write approvals are tool-level and cannot restrict method/event arguments;
inspect approvals rather than granting broad permanent permissions.



## Progressive publication references

The agent's operating contract is service-neutral. After identifying a remote
target and publication intent, it loads `review-publication/SKILL.md` and only
the matching service guide under `references/`. Report-only reviews need none
of these references. The GitHub guide includes MCP publication and explicitly
authorized `gh` fallback through an available, approved shell, or caller-supplied
results when execution is unavailable. A fallback never bypasses transport
authorization, source-write restrictions, or review-state checks.

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
