---
name: research-deep
description: Read a research outline and conduct independent deep research for each item. Use after outline.yaml and fields.yaml have been prepared.
license: MIT
---

# Research Deep - Deep Research

## Trigger
Use this workflow when the user asks to execute deep research from an existing outline.

## Workflow

### Step 1: Auto-locate Outline
Find a `*/outline.yaml` file in the current working directory, then read the topic, topic_dir, items list, and execution config, including items_per_agent. Require `topic_dir` to match `[a-z0-9]+(?:-[a-z0-9]+)*` and the exact parent directory name; stop with an error if it does not. Treat that parent as the canonical project directory and do not reconstruct it from `topic`.

### Step 2: Build Output Mapping and Resume Check
Before checking existing results or starting any worker, build one authoritative output path mapping for every item:

1. Reject the outline if two items have the same exact `name` value.
2. Resolve `execution.output_dir` (default: `./results`) relative to `{project_dir}` when it is a relative path. Use the resolved absolute directory as `{output_dir}`.
3. Derive each base slug from the exact item name by replacing each run of whitespace with `_`, removing every character other than ASCII letters, digits, `_`, and `-`, and trimming leading or trailing `_` and `-`. Use `item` when this produces an empty string. The slug must be one filename component, never a path.
4. Initially assign `{base_slug}.json`. Compare candidate filenames case-insensitively so the mapping is also safe on case-insensitive filesystems. For every collision, append `_<digest>` before `.json`, where `digest` starts as the first 8 lowercase hexadecimal characters of SHA-256 over the exact item name encoded as UTF-8.
5. Re-check all candidate filenames after each disambiguation pass, including collisions between a disambiguated filename and another base filename. For each still-colliding disambiguated item, extend its digest prefix by one character and check again. Stop with an error rather than execute if distinct names still collide after the full digest is used.
6. Store the resulting `{item_name}` to absolute `{output_path}` mapping and use it unchanged for both resume checks and worker prompts. Never recompute a slug in a worker. Verify all mapped paths are direct children of `{output_dir}` and are unique before starting execution.

Check only the mapped output path for each item and skip that item when its completed JSON file already exists. This mapping prevents two items, such as `C` and `C++`, from reading or writing the same result file.

### Step 3: Batch Execution
- Process items in batches according to batch_size and obtain user approval before starting each next batch
- Each research worker handles items_per_agent items
- Delegate to independent web-search agents in parallel when the harness provides agent delegation; otherwise process the items directly with the same isolation and prompts
- Use background execution when available, but do not depend on background-task behavior

**Parameter Retrieval**:
- `{topic}`: topic field from outline.yaml
- `{project_dir}`: absolute path to the parent directory of the outline found in Step 1
- `{item_name}`: item's name field
- `{item_related_info}`: item's complete yaml content (name + category + description etc.)
- `{output_dir}`: resolved absolute output directory; resolve a relative execution.output_dir from `{project_dir}` (default: `{project_dir}/results`)
- `{fields_path}`: absolute path to {project_dir}/fields.yaml
- `{output_path}`: absolute path assigned to the exact item name by the authoritative mapping in Step 2
- `{validator_path}`: path to `validate_json.py`, located beside the installed `research/SKILL.md`; resolve it relative to that skill resource rather than assuming a harness-specific absolute path

**Hard Constraint**: The following prompt must be strictly reproduced, only replacing variables in {xxx}, do not modify structure or wording.

**Prompt Template**:
```python
prompt = f"""## Task
Research {item_related_info}, output structured JSON to {output_path}

## Field Definitions
Read {fields_path} to get all field definitions

## Output Requirements
1. Output JSON according to fields defined in fields.yaml
2. Mark uncertain field values with [uncertain]
3. Add uncertain array at the end of JSON, listing all uncertain field names
4. All field values must be in English

## Output Path
{output_path}

## Validation
After completing JSON output, run validation script to ensure complete field coverage:
python3 {validator_path} -f {fields_path} -j {output_path}
Task is complete only after validation passes.
"""
```

**One-shot Example** (assuming researching GitHub Copilot):
```
## Task
Research name: GitHub Copilot
category: International Product
description: Developed by Microsoft/GitHub, first mainstream AI coding assistant, ~40% market share, output structured JSON to {project_dir}/results/GitHub_Copilot.json

## Field Definitions
Read {project_dir}/fields.yaml to get all field definitions

## Output Requirements
1. Output JSON according to fields defined in fields.yaml
2. Mark uncertain field values with [uncertain]
3. Add uncertain array at the end of JSON, listing all uncertain field names
4. All field values must be in English

## Output Path
{project_dir}/results/GitHub_Copilot.json

## Validation
After completing JSON output, run validation script to ensure complete field coverage:
python3 {validator_path} -f {project_dir}/fields.yaml -j {project_dir}/results/GitHub_Copilot.json
Task is complete only after validation passes.
```

### Step 4: Wait and Monitor
- Wait for the current batch to complete
- Display progress
- Ask for approval before launching the next batch

### Step 5: Summary Report
After all complete, output:
- Completion count
- Failed/uncertain marked items
- Output directory

## Execution Characteristics
- Parallel or background execution: Use when supported, but not required
- Worker output: Results are written to the explicit output file
- Resume support: Yes
