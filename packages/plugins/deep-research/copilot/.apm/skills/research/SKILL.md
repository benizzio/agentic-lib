---
# Generated from source/skills/research/SKILL.md; do not edit.
name: research
description: Conduct preliminary research on a topic and generate a structured research outline. Use for academic research, benchmark research, technology selection, and similar investigations.
license: MIT
---

# Research Skill - Preliminary Research

## Trigger
Use this workflow when the user asks to begin structured research on a topic.

## Workflow

### Step 1: Generate Initial Framework from Model Knowledge
Based on topic, use the model's existing knowledge to generate:
- Main research objects/items list in this domain
- Suggested research field framework

Output {step1_output}, then ask the user and wait for confirmation:
- Need to add/remove items?
- Does field framework meet requirements?

### Step 2: Web Search Supplement
Ask the user for a time range (e.g., last 6 months, since 2024, unlimited) and wait for a response.

**Parameter Retrieval**:
- `{topic}`: User input research topic
- `{YYYY-MM-DD}`: Current date
- `{step1_output}`: Complete output from Step 1
- `{time_range}`: User specified time range

**Hard Constraint**: The following prompt must be strictly reproduced, only replacing variables in {xxx}, do not modify structure or wording.

Delegate this prompt to one web-search agent. Use background execution when the harness supports it; otherwise wait for the delegated research to complete. If agent delegation is unavailable, perform the same web research directly using the prompt.

**Prompt Template**:
```python
prompt = f"""## Task
Research topic: {topic}
Current date: {YYYY-MM-DD}

Based on the following initial framework, supplement latest items and recommended research fields.

## Existing Framework
{step1_output}

## Goals
1. Verify if existing items are missing important objects
2. Supplement items based on missing objects
3. Continue searching for {topic} related items within {time_range} and supplement
4. Supplement new fields

## Output Requirements
Return structured results directly (do not write files):

### Supplementary Items
- item_name: Brief explanation (why it should be added)
...

### Recommended Supplementary Fields
- field_name: Field description (why this dimension is needed)
...

### Sources
- [Source1](url1)
- [Source2](url2)
"""
```

**One-shot Example** (assuming researching AI Coding History):
```
## Task
Research topic: AI Coding History
Current date: 2025-12-30

Based on the following initial framework, supplement latest items and recommended research fields.

## Existing Framework
### Items List
1. GitHub Copilot: Developed by Microsoft/GitHub, first mainstream AI coding assistant
2. Cursor: AI-first IDE, based on VSCode
...

### Field Framework
- Basic Info: name, release_date, company
- Technical Features: underlying_model, context_window
...

## Goals
1. Verify if existing items are missing important objects
2. Supplement items based on missing objects
3. Continue searching for AI Coding History related items within since 2024 and supplement
4. Supplement new fields

## Output Requirements
Return structured results directly (do not write files):

### Supplementary Items
- item_name: Brief explanation (why it should be added)
...

### Recommended Supplementary Fields
- field_name: Field description (why this dimension is needed)
...

### Sources
- [Source1](url1)
- [Source2](url2)
```

### Step 3: Ask User for Existing Fields
Ask the user whether an existing field definition file should be included. If so, locate or request its path, then read and merge it.

### Step 4: Generate Outline (Separate Files)
Merge {step1_output}, {step2_output} and the user's existing fields, then generate two files:

**outline.yaml** (items + config):
```yaml
topic: Research topic
items: Research objects list
execution:
  batch_size: Number of parallel agents (ask the user and wait for confirmation)
  items_per_agent: Items per agent (ask the user and wait for confirmation)
  output_dir: Results output directory (default: ./results)
```

**fields.yaml** (field definitions):
- Field categories and definitions
- Each field's name, description, detail_level
- detail_level hierarchy: brief -> moderate -> detailed
- uncertain: Uncertain fields list (reserved field, auto-filled in deep phase)

### Step 5: Output and Confirm
- Create directory: `./{topic_slug}/`
- Save: `outline.yaml` and `fields.yaml`
- Show to user for confirmation

## Output Path
```
{current_working_directory}/{topic_slug}/
  ├── outline.yaml    # items list + execution config
  └── fields.yaml     # field definitions
```

## Follow-up Workflows
- `research-add-items` - Supplement items
- `research-add-fields` - Supplement fields
- `research-deep` - Start deep research
