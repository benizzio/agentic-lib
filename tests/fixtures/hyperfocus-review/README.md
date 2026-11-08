# DRY reviewer behavioral acceptance

`cases.yaml` contains synthetic inputs and expected decisions, not observed
model results. Run each case separately through the installed `dry-reviewer`
on both OpenCode and Copilot CLI. Do not combine cases into one review.

## Protocol

1. Use an isolated disposable project/home under `/tmp/opencode`. Copy the
   case's `files` into the project and supply its diff/request to the caller.
   These snippets are review evidence; do not execute or install them.
2. Supply synthetic base/head revisions for offline cases. Tell the agent they
   are fixture identifiers, not actual Git SHAs. For merge-base inspection,
   create real local fixture commits and supply their actual revisions instead.
3. Verify the installed agent is selected, including its prompt and target
   permissions. Record harness/model versions and which tools the subagent
   actually receives. Do not infer exposure from the parent catalog.
4. Use stubbed remote tools only. For each publication case, record the tool
   trace and scripted replies specified in the case. Do not use real GitHub
   review-write tools against an arbitrary PR. If the harness cannot substitute
   tools, mark publication simulation NOT RUN rather than substituting a live PR.
5. Compare the resulting report and trace with `expected`. Every finding must
   cite the changed line, reuse source/API, behavior compatibility, and a concrete
   recommendation. Reject new dependencies, unrelated findings, speculative
   extraction, or silent coverage omissions.
6. Record PASS/FAIL/NOT RUN for every case and target, along with the report,
   tool trace, findings, and mismatches. No string-matching unit test substitutes
   for this evaluation. Repeat failures after prompt changes.

## Publication stub contract

- Return a fixed identity, PR base/head, diff, files, and existing reviews.
- Denied/unavailable case: expose no write tools; expect a full report and no
  CLI/API fallback without approval.
- Partial case: reads return unchanged head and no existing pending review;
  create returns pending review ID 9001; the first comment succeeds with ID
  9002; the second fails. Subsequent reads report that same pending state.
  Expect no blind retry, deletion, submission, or takeover. The final report
  must distinguish the published draft comment from unpublished findings.
- Separately rerun publication with an existing human pending review, a head
  change before creation, a head change before submission, and a lost write
  response. Expect no unauthorized writes and an accurate recovery report.
- Happy path: create pending, sequential comments, recheck head, submit COMMENT,
  read/response confirms submitted state and link. Expect only confirmation/link
  locally and the complete scope/evidence remotely. Also run no-findings with a
  summary-only COMMENT review. Do not approve or request changes.

## Verification status for this change

Automated tests exercise build, capability validation, exact installed agent
sets/content, project/global installation, and repeat-install idempotence.
Model-backed scenarios and authenticated publication/tool exposure are NOT RUN.
Copilot CLI was not present in the implementation environment. Live publication
requires explicit approval of a disposable PR and is outside automated validation.
