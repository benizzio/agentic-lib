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
Find a `*/fields.yaml` file in the current working directory, retain its exact path, and read the existing field definitions.

### Step 2: Get Supplement Source
Ask the user to choose:
- **A. User direct input**: User provides field names and descriptions
- **B. Web Search**: Delegate to the web-search agent to search common fields in this domain when agent delegation is available; otherwise perform the same web research directly

### Step 3: Validate and Merge
- Display the suggestions and ask which fields to add, including category and detail_level
- Treat the exact `name` string as field identity; do not normalize it differently between checks
- Reject suggestions containing duplicate names
- For each confirmed suggestion, skip an existing same-name definition when it is byte-equivalent or has identical category, description, detail_level, and required values
- Reject a same-name definition when any of those values differ
- Merge only the remaining suggestions into the existing definitions
- Build the complete candidate document in memory without writing to disk

### Step 4: Confirm and Save
Display the candidate, ask the user to confirm it, then atomically replace only the exact file found in Step 1. Do not write any file before confirmation.

## Output
Report the exact path found in Step 1 and whether it was updated; do not use a topic placeholder.
