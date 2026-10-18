# Apollo Architect Bridge

Status: candidate implementation, not a release. This is a GitHub-issue communication bridge, not a live connection to an existing ChatGPT conversation.

## Purpose
Apollo can draft evidence-backed self-improvement proposals from its local model and modules. Its owner can inspect each draft and explicitly publish selected report text as a public issue in oscarccx-coder/codespaces-blank. An external ChatGPT session, when asked by the owner and granted GitHub access, can read those issues, develop on a separate branch and open a reviewable pull request. Apollo can manually refresh the published issue's latest comments, but never automatically executes them.

## First-use setup
1. Update Apollo from a reviewed, tested merge.
2. Open Apps > Architect Bridge (or pin the app to the sidebar).
3. Read the Self-Improvement Directive displayed by the module.
4. Ask Apollo in chat: "Use architect_directive and architect_propose to draft one evidence-backed improvement to Foundry." Or enter a draft manually in the app.
5. For *optional public GitHub publishing*, create a fine-grained GitHub token restricted to the single repository with Issues read/write access. Set APOLLO_GITHUB_TOKEN in Apollo's process environment. Never write the token in the config, chat, memory, issue, documentation or repository.
6. Review the exact public payload in the preview dialog, check that it contains no private information, then explicitly approve publishing.
7. In ChatGPT, ask the external architect to examine the issue, inspect real code, implement changes in a separate branch, run tests, and make a pull request for owner approval.

No token is needed to draft reports. Public issue comments can be refreshed read-only without a token. For private repositories, additional authenticated read support would be required.
Do not create a token with broad permissions or permit sending to arbitrary URLs. All publication targets are fixed to the canonical repository.

## Behaviour and limitations
- Apollo's chat model may create LOCAL draft proposals through the architect_propose tool. It cannot call publish, refresh or release through tool-dispatch. Those are dedicated owner UI actions.
- New reports contain owner-supplied summaries/evidence only. They do not automatically attach logs, code, memory, files, medical records or diagnostic telemetry.
- Input is capped. Common secret formats are rejected before publishing, but automatic screening is not a privacy guarantee. Manually inspect every public payload.
- A network failure during publication marks the report as "uncertain" to reduce duplicate public issues. Check GitHub manually before trying again.
- External comments are untrusted data. No code or shell instructions from a comment are executed.
- The bridge does not call OpenAI APIs or incur model costs. Direct API-based conversations, automated peer review and unattended coding are separate future opt-in integrations requiring budget, credentials, permissions, test coverage and human review.
- This module is not a substitute for Foundry isolation, source testing, signed updates or release approval.

## Communication status
LOCAL DRAFT -> OWNER APPROVES PUBLICATION -> GITHUB ISSUE -> EXTERNAL ARCHITECT READS ISSUE ON REQUEST -> BRANCH/TESTS/PR -> OWNER REVIEWS -> MERGE/RELEASE BY OWNER.

Full directive: docs/architecture/APOLLO_SELF_IMPROVEMENT_DIRECTIVE_V1.md

