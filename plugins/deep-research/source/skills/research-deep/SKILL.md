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
Find a `*/outline.yaml` file in the current working directory, then read the items list and execution config, including items_per_agent.

### Step 2: Resume Check
- Check completed JSON files in output_dir
- Skip completed items

### Step 3: Batch Execution
- Process items in batches according to batch_size and obtain user approval before starting each next batch
- Each research worker handles items_per_agent items
- Delegate to independent web-search agents in parallel when the harness provides agent delegation; otherwise process the items directly with the same isolation and prompts
- Use background execution when available, but do not depend on background-task behavior

**Parameter Retrieval**:
- `{topic}`: topic field from outline.yaml
- `{item_name}`: item's name field
- `{item_related_info}`: item's complete yaml content (name + category + description etc.)
- `{output_dir}`: execution.output_dir from outline.yaml (default: ./results)
- `{fields_path}`: absolute path to {topic}/fields.yaml
- `{output_path}`: absolute path to {output_dir}/{item_name_slug}.json (slugify item_name: replace spaces with _, remove special chars)
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
