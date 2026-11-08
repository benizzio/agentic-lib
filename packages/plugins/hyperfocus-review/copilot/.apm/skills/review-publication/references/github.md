# GitHub pull request publication

Use only after confirming the repository, PR, publication intent, and approvals.
Prefer available, permitted GitHub MCP tools. Discover their current schemas;
server names and subagent exposure vary between installations.

## Common preflight and recovery

- Verify identity, reviewed base/head, existing reviews/comments, and diff anchors.
- Do not append to, submit, or delete a pending review created outside this
  invocation. If one exists, stop publication and return the complete report.
- Check the head before creating a review and again before submission. Stop on
  changes and disclose any pending state already created.
- Add comments sequentially. Do not invent inline locations; put unanchorable
  findings in the review body. Include full evidence, scope, reviewed revisions,
  coverage limits, and non-inline findings. No findings is valid, not approval.
- Submit only a COMMENT review. Never approve, request changes, resolve threads,
  merge, delete review state, or silently submit an incomplete review.
- After a failed or ambiguous write, inspect state before any further write.
  Do not blindly retry. Return IDs/links, pending/submitted state, and the full
  report distinguishing draft comments, submitted findings, and unpublished ones.
- Confirm submitted state and its link before claiming successful publication.
  Otherwise return a complete report with the accurate remote state.

## MCP sequence

1. Use `get_me` and `pull_request_read` for preflight. Inspect existing reviews
   and comments, and verify that the current head is the reviewed head.
2. `pull_request_review_write` with `method: create`, the reviewed `commitID`,
   and no `event`, to create a new pending review. Record its ID.
3. `add_comment_to_pending_review` for each finding, sequentially, using valid
   diff paths, lines, and sides. Keep unanchorable findings in the review body.
4. Recheck the head and submit only this invocation's pending review with
   `pull_request_review_write`, `method: submit_pending`, `event: COMMENT`.
5. Confirm submitted state and return the review link. A pending review or an
   ambiguous tool response is not proof of submission.

## Explicitly authorized GitHub CLI fallback

The user may authorize `gh` when MCP is missing, insufficient, or denied. MCP
failure alone is not authorization. Ask for and receive explicit permission
covering the target and read/write operations before using this transport.
Do not treat publication intent or a tool approval as blanket CLI authorization.

The reviewer must not acquire shell, editing, or unrestricted execution access.
Ask the caller to run the approved commands and return their results. Supply
the exact target, reviewed head, findings, and required state checks. If the
caller cannot execute them, return the full report with publication unavailable.

The caller should verify its installed `gh` help/API contract before execution.
Use `gh api` for the same pending-review lifecycle, not an unverified shortcut:

1. Read `user`, the PR, existing reviews/comments, and diff metadata. Paginate
   as necessary; stop if the state needed for safety checks is unavailable.
2. Create a review through `POST repos/{owner}/{repo}/pulls/{pull_number}/reviews`
   with `commit_id` set to the reviewed head and no `event`. Record the returned
   pending review ID; do not create a submitted review at this step.
3. Add findings sequentially using a verified GraphQL operation that attaches
   threads/comments to this pending review's node ID, through `gh api graphql`.
   Discover the current input schema and supported diff anchors first. The REST
   review-comments listing endpoint is not a draft-comment creation endpoint.
   If no supported draft-comment operation is available, retain those findings
   in the review body rather than posting standalone submitted comments.
4. Recheck the head, then submit this review through
   `POST repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/events`
   with `event: COMMENT` and the complete summary body.
5. Read back the review to confirm submitted state and URL.

These are API endpoint templates, not shell commands. Pass structured JSON
through `gh api --input -` with safely supplied standard input; never interpolate
source text into shell code.
Do not request credentials, change authentication, edit repository files, or
run mutating Git commands. The same duplicate, stale-head, failure, and recovery
rules apply to MCP and CLI. Inspect remote state before switching transports
after an ambiguous write, so a fallback cannot duplicate a review.

References: [GitHub CLI API](https://cli.github.com/manual/gh_api),
[review REST API](https://docs.github.com/en/rest/pulls/reviews),
[GraphQL reference](https://docs.github.com/en/graphql/reference).
