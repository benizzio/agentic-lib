# Publication safeguards

These rules apply to the orchestrating skill only. Reviewers always return their
complete reports and never write remote review state.

Discover the remote version-control review service and the permitted tools
actually exposed to the caller. Before acting, inspect live tool schemas and
current documentation for capabilities, selection semantics, and side effects;
do not assume a service or frozen API workflow. If schemas, documentation,
capabilities, or permissions needed for safe publication are unavailable, return
the consolidated new findings with that limitation.
GitHub PR review comments are one example, not a requirement or proof of support
for other services. Discovery does not provision missing tools or permissions.

Follow the consuming environment's external-service policies, including for
documentation access. Do not send private source or credentials in search queries
or URLs. Do not search the machine for credentials or private data to gain access
to tools. If needed operations are not exposed, ask the caller for their results
or return the consolidated report. If questions or approval are unavailable,
report locally rather than bypassing controls.

Before any remote write:

1. Confirm the service, repository, remote review target, caller publication
   intent, and required approvals. Invoking this skill authorizes its default
   supported publication workflow unless the caller restricts it; it does not
   override host policies or required approvals. A branch diff alone does not
   identify a remote review target. Honor report-only requests with no publication
   writes; clarify ambiguous targets or conflicting intent.
2. Verify the current identity and refresh existing reviews/comments for
   deduplication. Do not touch pending reviews outside this invocation. If pending
   state from outside this invocation is found, stop publication and report it.
3. Verify the reviewed revision and, for changed-code reviews, both base and head
   AND comparison consistency against the remote target, using the detected
   system's equivalents. A retargeted base with the same head is still stale.
   Uncommitted/local-only snapshots are not equivalent to a remote revision.
   Repeat this check before submission. If anything changed, stop and ask for a
   new review; disclose any pending state for human recovery rather than attaching
   stale findings. Local reporting must label the actual reviewed snapshot.
4. Establish a permitted, comment-only, non-approval publication operation from
   the live service contract. If it uses pending reviews, verify that subsequent
   mutations and submission can provably target the invocation-owned review by
   its recorded identifier. Current-user pending-review selection is not safe
   ID binding: another review can replace it. If safe binding is unavailable,
   use only an explicitly authorized equivalent operation or stop with the full
   consolidated report; never silently fall back to a different operation or
   transport.

Capture created review/comment IDs and links. Add findings sequentially, only
at anchors validated against the reviewed revision and current remote diff.
Put unanchorable findings, including whole-codebase or unchanged locations
outside the diff, in the review summary with precise source references; never
invent diff anchors. Include full scope, evidence, reviewer attribution, coverage
and history limitations remotely. Suppressed findings must not reappear in
summaries. No findings is valid and may use a summary-only review when supported,
subject to the skill's no-new-findings and repeated-summary rules.

Do not approve, request changes, resolve threads, merge, or delete review state.
This focused review does not establish merge readiness. Use equivalent operations
on other services only when actually exposed and permitted; do not claim
unsupported MR support.

If any write fails or its outcome is ambiguous, inspect remote state before
further writes. Do not blindly retry, switch transports, or silently submit an
incomplete review. Continue only when state, invocation ownership, valid anchors,
and completeness can be established safely; otherwise stop and return the
consolidated new findings with accurate pending/submitted/unknown state, recorded
IDs/links, and published versus unpublished findings. Pending comments are not
submitted findings. Confirm submission from service evidence before claiming
success, and update the run record accordingly. An acknowledged write alone is
not proof of submission. Never repeat a confirmed published finding locally as
if it were unpublished.
