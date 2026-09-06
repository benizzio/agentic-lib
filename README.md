# agentic-lib

Portable agent artifacts packaged with
[Microsoft APM](https://github.com/microsoft/apm).

## Prerequisites

- [Microsoft APM](https://microsoft.github.io/apm/getting-started/installation/)
  `v0.29.1` installed and available on `PATH`.
- Python 3.10 or newer with the standard-library `venv` module for maintaining
  the repository.

Verify the installation with `apm --version`.

## Source Layout

- `apm.yml` and `.apm/` define the independent root artifacts package.
- `plugins/*/source/` and `plugins/*/targets/` are canonical plugin sources and
  target overlays.
- `plugins/*/plugin.yml` defines shared metadata, lockstep package versions, and
  artifact mappings.
- `packages/plugins/` contains generated, Git-installable target package roots.
  These files are committed but must not be edited manually.
- `apm_modules/` and `build/` are local APM output and are not source files.

## Available Artifacts

### Instructions

#### `global-AGENTS`

Instructions required in every session of the selected harness. APM compiles
this source into the selected harness's global context file.

### Skills

#### `bulk-address-github-review-comments`

An [Agent Skill](https://agentskills.io/) for processing unresolved GitHub
pull request review threads as a confirmed, sequential queue. It delegates
each atomic implementation unit to one sub-agent, verifies the resulting work,
then commits and pushes completed atomic work units as needed. One work unit
may satisfy multiple review threads without empty commits; review-thread
replies remain sequential and occur one thread at a time.

#### `github-etiquette`

An [Agent Skill](https://agentskills.io/) for Git repositories with a GitHub
remote. It requires confirmation before committing on the repository's
configured default branch, requires every GitHub pull request to start as a
draft, and adds an issue-closing reference when the related issue is known.

### Plugin Packages

#### Deep Research

An adapted fork of
[Weizhena/Deep-Research-skills](https://github.com/Weizhena/Deep-Research-skills)
containing a web-search agent, five search strategy modules, and five English
research skills. OpenCode and GitHub Copilot CLI receive separate package
variants so each agent has compatible frontmatter. See
[`plugins/deep-research/UPSTREAM.md`](plugins/deep-research/UPSTREAM.md) and the
preserved [`UPSTREAM_LICENSE`](plugins/deep-research/UPSTREAM_LICENSE).

##### Install

For a project installation, use each package with its matching target. Install
the OpenCode variant with:

```bash
apm install benizzio/agentic-lib/packages/plugins/deep-research/opencode --target opencode
```

Install the GitHub Copilot CLI variant with:

```bash
apm install benizzio/agentic-lib/packages/plugins/deep-research/copilot --target copilot
```

Add `--global` to the Copilot command for a user-scope installation. For a
global OpenCode installation with APM `v0.29.1`, install the shared skills and
OpenCode agent separately:

```bash
apm install benizzio/agentic-lib/packages/plugins/deep-research/opencode \
  --target agent-skills --global
apm install \
  benizzio/agentic-lib/packages/plugins/deep-research/opencode/.apm/agents/web-search.agent.md \
  --target opencode --global
```

OpenCode supplies web search when using its provider. With another provider,
enable Exa when starting OpenCode:

```bash
OPENCODE_ENABLE_EXA=1 opencode
```

Install the validator dependency in the Python environment where the research
skill will run. For a project installation:

```bash
python3 -m pip install -r .agents/skills/research/requirements.txt
```

For a global OpenCode installation with APM `v0.29.1`:

```bash
python3 -m pip install -r ~/.agents/skills/research/requirements.txt
```

APM does not install this Python dependency automatically.

##### Use

Run the workflow from the repository where the research output should be
created. Invoke the installed skills with the following slash commands in
sequence.

1. Generate the research outline:

   ```console
   /research AI Agent Demo 2025
   ```

   This creates `<topic>/outline.yaml` with the items to investigate and
   `<topic>/fields.yaml` with the information to collect for each item.

2. Optionally refine the outline before starting deep research:

   ```console
   /research-add-items
   /research-add-fields
   ```

3. Research every item in approved batches:

   ```console
   /research-deep
   ```

   This writes one validated JSON result per item to the output directory
   configured in `outline.yaml`. The workflow can resume by skipping completed
   results.

4. Generate the final report:

   ```console
   /research-report
   ```

   This creates `<topic>/generate_report.py` and `<topic>/report.md`.

## Install

This section applies to the repository's root APM package. Plugin packages have
their own installation instructions under [Plugin Packages](#plugin-packages).

The `agent-skills` target deploys skills only. It does not install other
artifact types from this package.

### Install Global Instructions For OpenCode

Install the complete root package's skills at user scope first:

```bash
apm install benizzio/agentic-lib --target agent-skills --global
```

For a fresh user-scope installation, this creates `~/.apm/apm.yml` with
`agent-skills` declared. If the manifest already exists, the explicit install
target is one-shot and does not update its `targets:` list. After installation,
ensure that list retains every existing target and includes both `agent-skills`
and `opencode`. For example:

```yaml
targets:
  - agent-skills
  - opencode
```

`apm compile --global` reads the manifest rather than the preceding install
command, so it produces no OpenCode context file unless `opencode` is declared
there. After updating the manifest, explicitly compile the instructions into
OpenCode's global context file:

```bash
apm compile --global --dry-run
apm compile --global
```

The install command stages the package under `~/.apm/` and deploys its skills
under `~/.agents/skills/`. The dry run previews compilation without writing
files, and the final command writes the APM-managed
`~/.config/opencode/AGENTS.md`. APM `v0.29.1` reads the global manifest's
`targets:` declaration, so an OpenCode-only manifest does not create context
files for unrelated harnesses.

To install only the global instruction without this package's skills, use its
source file as a virtual package:

```bash
apm install \
  benizzio/agentic-lib/.apm/instructions/global-AGENTS.instructions.md \
  --target opencode \
  --global
apm compile --global --dry-run
apm compile --global
```

APM does not overwrite a hand-authored `~/.config/opencode/AGENTS.md`.
Incorporate its required content into the packaged instruction, back it up,
remove it, and then compile. Restart OpenCode after the generated file changes.

### Install All Skills

Run this command from the repository where every published skill should be
available:

```bash
apm install benizzio/agentic-lib --target agent-skills
```

This installs each skill under `.agents/skills/<skill-name>/`, the
harness-agnostic shared location.

Preview the all-skills installation without writing target files:

```bash
apm install benizzio/agentic-lib --target agent-skills --dry-run
```

### Install One Skill

Pass the skill name with `--skill` during the initial package installation:

```bash
apm install benizzio/agentic-lib --skill github-etiquette --target agent-skills
```

Replace `github-etiquette` with another name listed under
[Skills](#skills).

### Install Other Artifact Types

This repository is an
[APM package](https://microsoft.github.io/apm/reference/package-types/): a
collection of independent primitives authored under `.apm/`. APM deploys each
primitive supported by the selected target and skips unsupported types.

Use one or more harness-specific
[supported targets](https://microsoft.github.io/apm/reference/targets-matrix/)
to install agents, commands, hooks, MCP configuration, or other supported
artifacts. Artifact support and destination paths differ by target.

For example, install every artifact supported by the OpenCode target with:

```bash
apm install benizzio/agentic-lib --target opencode
```

Preview the OpenCode installation without writing target files:

```bash
apm install benizzio/agentic-lib --target opencode --dry-run
```

#### Install One OpenCode Artifact

APM supports different selection mechanisms by artifact type. Replace the
placeholder names below only after the artifact is listed under
[Available Artifacts](#available-artifacts).

Install one skill from this package:

```bash
apm install benizzio/agentic-lib --skill github-etiquette --target opencode
```

Install one agent as a virtual file package:

```bash
apm install benizzio/agentic-lib/.apm/agents/AGENT_NAME.agent.md --target opencode
```

Install one command from its canonical prompt source as a virtual file package:

```bash
apm install benizzio/agentic-lib/.apm/prompts/COMMAND_NAME.prompt.md --target opencode
```

Install one MCP server directly from an MCP registry:

```bash
apm install --mcp REGISTRY_SERVER_NAME --target opencode
```

The MCP command adds the server directly to the consuming project; it does not
select one MCP dependency from this package. APM has no per-server selector for
package-declared MCP dependencies.

OpenCode does not support hooks. Prompts become OpenCode commands, and
instructions are compiled into context rather than installed as native
instruction files.

#### Install an APM Plugin Bundle

In APM terminology, a plugin is a distribution bundle identified by
`plugin.json` or `.claude-plugin/`. It contains a set of primitives such as
skills, agents, commands, hooks, and MCP definitions; it is not an individually
routed primitive. `apm pack` can convert this APM package into a plugin bundle.

Install a complete plugin from a configured marketplace with:

```bash
apm install PLUGIN_NAME@MARKETPLACE --target opencode
```

APM unpacks the complete plugin and routes each contained primitive supported
by the OpenCode target. Use the single-artifact commands above only when an
individual primitive must be selected instead.

Add `--global` to install at user scope instead of project scope. Pin a release
tag or commit with `benizzio/agentic-lib#<ref>` when reproducible installation
is required.

## Maintain

Edit root package skills under `.apm/`. For generated plugins, edit only
`plugins/<name>/source/`, `plugins/<name>/targets/`, and `plugin.yml`. The build
copies canonical artifacts, replaces eligible top-level frontmatter with the
selected target overlay, and writes installable roots under `packages/plugins/`.
Source and generated output must be committed in the same pull request.

Install the pinned build dependency, generate packages, and run all validation:

```bash
make setup
make build
make validate
git add -A
```

`make setup` creates `.venv/` and installs `requirements-build.txt` there, so it
works with externally managed system Python installations. Activating the
environment is unnecessary: the remaining Make targets use `.venv/bin/python`
automatically. Override `VENV`, `BOOTSTRAP_PYTHON`, or `PYTHON` when a custom
environment or interpreter is required.

`make check` is read-only and fails if committed packages are missing, changed,
or stale. `make validate` additionally runs builder and validator unit tests,
APM audits and dry packs, and real project/global installs with APM `v0.29.1`.
APM does not invoke this repository's builder during installation.

To live-test a pushed feature branch, append `#<branch>` after the package
subdirectory. Quote the source when the branch name contains `/`. Preview and
then install the OpenCode package from a disposable consumer project with:

```bash
apm install \
  'benizzio/agentic-lib/packages/plugins/deep-research/opencode#feat/example' \
  --target opencode \
  --dry-run
apm install \
  'benizzio/agentic-lib/packages/plugins/deep-research/opencode#feat/example' \
  --target opencode
```

Add `--skill research-add-items` to select one skill from the package. Add
`--global` to install at user scope. APM uninstalls Git packages by their source
locator, not the package name in the generated `apm.yml`. Omit the Git ref from
the install source when uninstalling:

```bash
apm uninstall benizzio/agentic-lib/packages/plugins/deep-research/opencode
apm uninstall --global benizzio/agentic-lib/packages/plugins/deep-research/opencode
apm uninstall --global \
  benizzio/agentic-lib/packages/plugins/deep-research/opencode/.apm/agents/web-search.agent.md
```

To add a plugin, create `plugins/<name>/plugin.yml`, canonical artifacts under
`source/`, and one or more `targets/<target>.yml` overlays. To add a target to an
existing plugin, add its target file. The generic builder discovers both without
changes to `scripts/build.py`. Increment the shared version in `plugin.yml`; all
target variants use that version in lockstep. Run `make build` after every source,
mapping, metadata, or target change.
