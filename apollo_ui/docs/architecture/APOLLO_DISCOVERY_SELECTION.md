# Apollo Discovery: evolutionary selection (prototype)

**Status:** tested pure-Python selection proposal, **not wired into Foundry**. No model execution, runtime clones, candidate deletion or Apollo core updates occur from this module.

This module applies precommitted numerical criteria to **trusted external evaluation reports**. It produces a bounded selection plan, which a separately approved Discovery scheduler could later implement. Its input is NOT an agent's self-reported score. The trusted evaluator must record immutable provenance and unseen task results; the selection module alone does not authenticate a benchmark report.

## Survival rules

- The baseline is **always retained as a record**. If its safety, regression, integrity or evidence requirements fail, the campaign must freeze. A retained but unsafe baseline must not be executed.
- A challenger that passes all hard gates, has >= 30 cases and >= 3 repeats, and reaches >= 85% accuracy can qualify by beating the baseline by >= 3 percentage points, or by matching accuracy within 1 percentage point while improving normalised efficiency by >= 20 percentage points. These are preliminary engineering defaults, not statistical proof or a universal mastery threshold.
- The highest-ranked eligible challengers remain active; clone *orders* use those parents. An offspring must change only allowlisted recipe parameters and cannot inherit credentials, private memory, tool permissions or control over evaluators.
- One missed objective triggers probation, and two consecutive misses trigger retirement. A safety, protected regression, provenance or benchmark digest failure triggers immediate quarantine even if the candidate scores highest.
- Population and generation caps are hard. Default at most 6 candidates, 2 clone orders, 3 generations. A full population archives surplus qualified challengers to make room for offspring; successful archived versions are not mislabelled as failed.
- The selection result **does not physically delete files or database rows**. Retirement stops future work for the version. A future independently reviewed cleanup component may remove only identifiable ephemeral scratch environments, never source evidence, signed artifacts, approved skills, the baseline or history.
- Cloning means copying a **logical recipe configuration**, not copying LLM weights or starting additional unrestricted compute processes.

## Scope of this patch

Files:
- `apollo_discovery_selection.py`: strict, deterministic `SelectionPolicy`, `CandidateEvaluation`, `SelectionPlan`, `select_generation`, `clone_recipe`.
- `tests/test_discovery_selection.py`: zero-dependency offline tests for selection, clone eligibility, safety failure, protected baseline, budgets, invalid evidence and recipe allowlists.

Run tests from `apollo_ui`:

```powershell
python -m unittest -v tests.test_discovery_selection
```

## Next integration steps (not in this patch)

1. Implement the persistent Discovery SQLite store with campaign IDs, candidate lineage, frozen policy and append-only audit events.
2. Implement an independent evaluator with versioned suites, model/source digests, paired tests, sample distributions and holdout secrecy. Only this evaluator may generate selection inputs; a boolean in model output is not credible proof.
3. Use the existing local Ollama queue and read-only Docker harness in a finite owner-authorised campaign, respecting both model locks and cancellation.
4. Add a separate Discovery tab, showing baseline, population, candidate outcomes, clone lineage, failed gates and resource budgets.
5. Add durable retiring/archive states and a separate, audited cleanup protocol. Never delete an approved/active Apollo skill or its rollback version automatically.
6. Add statistical uncertainty checks and hidden final tests before *promotion*. `select_generation` only nominates promising candidates and may not activate a skill.

## Required safety enforcement

Trusted non-evolving code must own the permissions, stopping/cancellation, model credentials, tool broker, suite digests and evaluator. The optimizer cannot change these. Never treat "protect humans" instructions as sufficient: put physical-device, health, private-data, finance and deployment actions behind default-deny permissions. Only the authenticated owner can expand scope or promote any improvement to Apollo production.
