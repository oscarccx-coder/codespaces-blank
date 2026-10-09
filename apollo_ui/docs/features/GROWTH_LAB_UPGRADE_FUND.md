# Apollo Growth Lab v1: fund useful hardware upgrades with approved paid work

Apollo's bottleneck is often hardware. **Apollo cannot earn, hold, send or spend
money independently.** Growth Lab is a user-directed upgrade planning and
bookkeeping tool, not an AI-controlled company or financial account.

## What is installed

Go to **Settings → Apps → Coding → Growth Lab**.

- **Hardware & Bottlenecks**: local read-only CPU thread count, free/total RAM,
  platform details and available NVIDIA GPU VRAM. This is a snapshot, not a
  measured model-performance comparison or guarantee an upgrade will help.
  Use GPU Monitor / Model Runtime and repeat actual Ollama throughput tests to
  determine whether VRAM, CPU, RAM, storage or context size are the limit.
- **Paid Work Plans**: a queue of assistant-created *draft proposals*.
  The model may suggest ideas and draft deliverables, but only a **person** can
  approve, claim delivery and record a payment. There are no live vacancies,
  external clients or contracts automatically discovered.
- **Upgrade Fund**: user-defined hardware targets, explicitly confirmed deposits,
  withdrawals and payments actually received. All money is stored as integer
  pence in the private SQLite database, with an audit trail. It is **not** a
  bank statement or real account balance. Creating an upgrade target does not
  purchase anything. No invoices, payments or financial transfers occur.

The core file is `apollo_growth.py`; the Qt app is
`modules/growth_lab/module.py`. Local state is stored under
`storage/databases/apollo_growth.db`, excluded from GitHub and
all signed update packages. The app works offline and without subscriptions.

## Proposal lifecycle

1. Apollo identifies a possible income-producing *service* and adds a **draft**.
   It cannot promise a sale or count an estimate as earned income.
2. The owner reviews scope, legality, payment terms and feasibility, then
   confirms **Approve Selected** in the UI. That only changes a planning state.
   It does not contact a client or accept a binding contract.
3. Work can be created in the isolated Coding Team workspace using the usual
   tests and human approval gates. Growth Lab **does not launch** that work.
4. Once the actual customer deliverable is done, the owner confirms
   **Mark Delivered**.
5. Once payment is genuinely received, the owner presses **Record Payment**,
   enters the actual GBP amount and a general receipt note, and manually
   confirms. Apollo cannot independently verify a bank transaction.
6. Growth Lab adds the confirmed amount to its **manual** upgrade-fund ledger.
   It does not move funds or reserve any real money. Funds remain wherever
   the owner actually keeps them.

The work queue enforces the `proposed → approved → delivered → paid`
status sequence. A paid job can be recorded only once. Old proposals can be
archived, without removing past entries.

Assistant tool APIs exposed by this module are *limited* to:
`growth_hardware_snapshot`,
`growth_opportunity_ideas`,
`growth_propose_work`,
`growth_work_queue` and
`growth_fund_status`.

The assistant tool bus **cannot** call the functions that approve projects,
record payments, create hardware targets or debit the fund.

## Sensible first deliverables

- Tested restaurant pre-order/workbook templates and stock trackers.
- Small business automation scripts with installation documentation and tests.
- Restaurant event promotional assets and social-content packs.
- Original electronics learning workbooks using CRUMB for demonstration,
  with real circuits independently checked against datasheets.
- User-approved website issue fixes and programming test reports.

These are **project concepts**, not actual open jobs or guaranteed revenue.
Opportunity research, platform rules, customer communication and prices need
human verification. The owner is responsible for taxes, business registration
where applicable, licensing, consumer rights and respecting client privacy.
Never scrape private job boards, automatically message prospects or submit
freelance applications without explicit permission.

## Next milestones (not yet installed)

1. Benchmarked upgrade advisor using sustained model **tokens/s**, failed
   loads, VRAM saturation, context and task success rates rather than
   instantaneous device status alone.
2. Dedicated product/service portfolio of demonstrably tested Apollo-built
   software and creative work, with per-project acceptance checks.
3. Bounded research assistant to suggest **real, permitted** opportunities for
   owner review. No applications, outreach, scraping or job acceptance without
   approval.
4. Work orchestration: connect a user-approved proposal to isolated Coding
   Team tasks, staged deliverables and tests, without granting autonomous
   external business authority.
5. Hardware ROI comparisons with verified local prices and measurements; never
   invent income or claim financial returns.

## Hardware strategy

First improve model settings, memory residency, batching and modular CPU/RAM
use. Then benchmark a Pi worker vs the local desktop, before committing to an
expensive GPU upgrade. Keep storage free for recovery snapshots and models.
When a larger model demonstrably needs more fast memory than the RTX 3060
provides, the owner can compare realistic upgrade prices and expected
performance, avoiding vanity hardware purchases based on model parameter
counts alone.

All purchases and transactions require the owner's approval outside Apollo.
