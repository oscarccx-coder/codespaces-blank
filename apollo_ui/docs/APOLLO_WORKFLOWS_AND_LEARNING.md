# Workflows & Learning: owner guide

See the [full feature plan](APOLLO_CHASE_ECC_IMPLEMENTATION_PLAN.md) for the W01–W12 implementation and acceptance map.

## Use the app

After updating, open **Chat → Apps → Workflows & learning** or find it in the Memory & Learning app group. Select one of the five finite workflows, enter a goal and choose **Start workflow**. Public research requires its web checkbox. Memory indexing is optional; choose an existing knowledge node or automatic Research/topic routing. Foundry assessment requires an existing project number.

Runs show saved stages, specialist roles, dependencies, attempts, wall times, last activity and actual errors. **Show latest handoff** displays a receipt hash and next action. **Read output** opens the completed report. Reports are saved as `storage/workflow_outputs/RUN_ID.md`; raw pages remain in Training's research store, and optional topic notes in Memory Bank.

The five workflows are public research brief, saved-knowledge brief, Foundry readiness assessment, local application benchmark and read-only configuration audit. Research quotations must match fetched text; saved-knowledge citations must use real retrieved IDs. These checks establish reference provenance, not factual truth. Foundry assessment reads static checks and source-matched test history without executing generated code, running tests or approving projects. Configuration audit reports redacted settings/permission findings; it is not AgentShield or a complete security audit.

## Chat commands

Enable Tools in a persistent chat:

- `list workflows`
- `start public workflow research about retrieval memory`
- `start public workflow research about retrieval memory save to node 42`
- `start workflow knowledge about retrieval memory`
- `start workflow benchmark about local reasoning`
- `start workflow audit about Apollo settings`
- `start workflow foundry project 3`
- `status workflow RUN_ID`
- `pause workflow RUN_ID`
- `resume workflow RUN_ID`
- `stop workflow RUN_ID`

Use the twelve-character ID Apollo returns. Only the newest actual owner message is a command channel. Model output/source text cannot start or approve work. Temporary chat cannot start workflows or access these tools.

## Recovery and limits

Runs are finite graphs of three or four stages, with a hard maximum of eight and no arbitrary shell operations. At most twelve queued/running/paused jobs are allowed. Cross-process run leases expire after ten minutes. Committed stages are not replayed; an uncommitted stage may retry after its stale lease expires. Runs wait until the module manager is ready after launch.

Pause prevents the next stage. Stop before work is immediate; during work, the current stage can finish and save a receipt, then the run stops permanently. Workflow model calls have a 90-second deadline. Failures block the run and remain visible. After fixing a problem, **Resume / retry** retries the failed stage. A failed memory save can therefore retry output without refetching sources; stable filenames and memory names prevent duplicate reports/memories.

Local generation requires the configured loopback Ollama server and rejects external endpoints/cloud-labelled models. It never silently changes your selected model or downloads one. Oversized context is refused rather than claimed to have been fully read. Tool permissions remain enforced by the existing broker.

## Reusable procedures

Two completed runs that passed their narrow deterministic contracts propose a reusable procedure. The Reviewed procedures tab shows supporting runs and failed stage attempts. Approve/name a candidate to run that known workflow again with a new goal, or revoke it to prevent new runs. Existing runs must be stopped separately. Approval grants no extra web/memory permissions and does not train weights or generate executable code.

## Knowledge, topic progress and practice

The Knowledge map identifies source receipts, topic memory, final outputs and work state. Notes are linked to the selected Knowledge Node and remain explicitly unverified research. Original sources are retained.

Topic progress aggregates up to 2000 persisted practice batches into concepts, observed scores and suggested review dates. Failed recall suggests review after one day; successful recall after seven days. These are review suggestions, not a second scheduler or mastery ratings.

Continuous practice remains in **Practice & learning**. It now adds a third local call for four fresh workload/evidence application problems, within the existing shared 120-second deadline. The answer key is withheld, grading is deterministic, and scores are separate from cloze recall. An application failure stays visible while preserving a valid source lesson. Weak application skills can guide subsequent topic-anchored research. Existing daily budgets, duplicate suppression and pause/stop controls remain unchanged.

## Auto routing and Foundry handoffs

Select **Auto** in the chat mode picker. Explicit research requests select Web/Deep research; explicit coding requests use existing guarded coding paths; other requests use Chat. Tools-off and temporary chats always select Chat. Routing preserves the selected model and grants no new permissions or cloud budget.

Foundry worker drafts and team meetings now receive bounded project-scoped persisted handoffs as reference context. They are not release approvals.

## Validation boundary

Automated tests use actual SQLite stores, real Memory Bank/Foundry integrations, deterministic model/source fixtures and real offscreen Qt controls. They test behavior and recovery, not live-model answer quality or broad intelligence improvement on the owner's PC. No new signed installer or local installation is implied by merging source.
