---
name: research-add-fields
description: Add field definitions to an existing research outline. Use when the user wants to supplement or revise fields.yaml.
license: MIT
---

# Research Add Fields - Supplement Research Fields

## Trigger
Use this workflow when the user asks to add fields to an existing research outline.

## Workflow

### Step 1: Auto-locate Fields File
Find a `*/fields.yaml` file in the current working directory and read the existing field definitions.

### Step 2: Get Supplement Source
Ask the user to choose:
- **A. User direct input**: User provides field names and descriptions
- **B. Web Search**: Delegate to the web-search agent to search common fields in this domain when agent delegation is available; otherwise perform the same web research directly

### Step 3: Display and Confirm
- Display suggested new fields list
- Ask the user to confirm which fields to add
- Ask the user to specify field category and detail_level

### Step 4: Save Update
Append confirmed fields to fields.yaml and save the file.

## Output
Updated `{topic}/fields.yaml` file (in-place modification, requires user confirmation)
