---
name: research-add-items
description: Add research objects to an existing research outline. Use when the user wants to supplement or revise the items in outline.yaml.
license: MIT
---

# Research Add Items - Supplement Research Objects

## Trigger
Use this workflow when the user asks to add items to an existing research outline.

## Workflow

### Step 1: Auto-locate Outline
Find a `*/outline.yaml` file in the current working directory, record its exact path, and read it. Require `topic_dir` to match `[a-z0-9]+(?:-[a-z0-9]+)*` and the exact parent directory name; stop with an error if it does not. Treat that parent as the canonical topic directory and do not reconstruct a path from `topic`.

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
Updated the exact `outline.yaml` path discovered in Step 1 (in-place modification)
