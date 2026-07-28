---
name: github-etiquette
description: >-
  Use whenever an agent is about to commit changes in a Git repository with a
  GitHub remote or create a pull request on GitHub. Enforces default-branch
  commit confirmation, draft pull requests, and issue-closing linkage.
---

# GitHub Etiquette

Apply these rules when the repository has a GitHub remote. Treat each commit
and pull request as a separate action that must satisfy the rules below.

## Before Every Commit

1. Determine the currently checked-out branch immediately before running the
   commit.
2. If the branch is `main` or `master`, stop before creating the commit.
3. Warn the user that committing directly to that branch violates basic GitHub
   etiquette because changes should be made on a feature branch.
4. Ask for explicit confirmation to create this specific commit on the default
   branch.
5. Run the commit only after the user gives positive confirmation. An absent,
   ambiguous, or negative response is not confirmation.

Confirmation applies only to the commit for which it was requested. Do not
reuse confirmation from an earlier commit.

## When Creating A Pull Request

1. Always create the pull request as a draft. For example, use `--draft` with
   `gh pr create` or set `draft: true` when using an API.
2. Determine whether an issue is related from the user's request and the known
   task context. Do not invent or guess an issue number.
3. When a related issue is known, add a GitHub closing keyword on its own line
   in the pull request body, such as `Closes #123`. Use the full issue URL when
   needed to identify an issue outside the pull request's repository.
4. Verify that both the draft state and issue-closing reference are present
   before submitting the pull request creation request.
