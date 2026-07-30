---
# Generated from source/skills/research-add-items/SKILL.md; do not edit.
name: research-add-items
description: Add research objects to an existing research outline. Use when the user wants to supplement or revise the items in outline.yaml.
license: MIT
---

# Research Add Items - Supplement Research Objects

## Trigger
Use this workflow when the user asks to add items to an existing research outline.

## Workflow

### Step 1: Auto-locate Outline
Find a `*/outline.yaml` file in the current working directory and read it.

### Step 2: Get Supplement Sources in Parallel
When parallel interaction and delegation are available, do these concurrently; otherwise do them sequentially:
- **A. Ask user**: What items should be supplemented? Any specific names?
- **B. Ask if Web Search is needed**: Delegate to the web-search agent to search for more items when available; otherwise perform the same web research directly

### Step 3: Merge and Update
- Append new items to outline.yaml
- Display the merged items to the user for confirmation
- Avoid duplicates
- Save the updated outline

## Output
Updated `{topic}/outline.yaml` file (in-place modification)
