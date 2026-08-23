# Upstream Provenance

This plugin contains adapted content from
[Weizhena/Deep-Research-skills](https://github.com/Weizhena/Deep-Research-skills)
at commit `e5479f857f484cde13fe69d2f3ce8de7af193bc7`.

Imported upstream paths:

- `agents/web-search-agent.md`
- `agents/web-search-modules/*.md`
- `skills/research-en/research/SKILL.md`
- `skills/research-en/research/validate_json.py`
- `skills/research-en/research-add-fields/SKILL.md`
- `skills/research-en/research-add-items/SKILL.md`
- `skills/research-en/research-deep/SKILL.md`
- `skills/research-en/research-report/SKILL.md`

Local changes make the content portable across supported agent harnesses. Source
frontmatter uses common fields, model selection is inherited from the harness,
tool references are capability-oriented, and installed resources are located
relative to the `research` skill instead of through harness-specific absolute
paths.

OpenCode provides web search when using the OpenCode provider. With other
providers, start OpenCode with `OPENCODE_ENABLE_EXA=1 opencode` to enable the
required Exa-backed web-search capability.

The validator includes the schema parsing and required-field behavior proposed
in upstream [PR #8](https://github.com/Weizhena/Deep-Research-skills/pull/8),
plus an explicit failure when no field definitions can be parsed. The upstream
PR was based on the pinned commit but was not merged at import time.

The upstream MIT license is preserved in `UPSTREAM_LICENSE` and is mapped into
generated packages with the research skill resources.
