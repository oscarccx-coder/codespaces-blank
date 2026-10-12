# Apollo Build 8 -> Beta -> Apollo 1.0

**Status: Build 8 is alpha/development. A public beta has NOT been approved or published by this change.**

Version 8.0.0.0 is a **development build identifier**, not the final
product major release. All agreed roadmap jobs and safety/recovery tests must
be evidenced before promoting an Apollo 8 beta. After full completion and sign-off,
the eventual first stable public product line will be **Apollo 1.0**.
Downgrading the current numeric version from 8.x to 1.x will require an
explicit, tested updater migration; never silently change the version field.

## Roadmap criteria and ownership

The printable "Apollo Beta Roadmap Jobs With Criteria" sheet defines a
specific PASS WHEN criterion for each job. The ID ranges are:

| Stage | Goal IDs | Count | Outcome |
|---|---|---:|---|
| P0 Recovery & updates | R01-R14 | 14 | Safe reinstall, protected data, rollback and signed update |
| P1 Daily UI | U01-U14 | 14 | Navigable, responsive, readable interface |
| P1 Memory, learning & reasoning | L01-L15 | 15 | Evidence-led retrieval, review and benchmarks |
| P2 Voice, vision & tools | V01-V15 | 15 | Real device operation, permissions and recovery |
| P3 Coding team | A01-A14 | 14 | Isolated, reviewed, budgeted multi-agent development |
| P4 Devices & expansion | F01-F14 | 14 | Pi, integration, safe peripherals and long-term protection |
| **Total** | | **86** | |

The checkboxes reflect separate stages:

* **Pending**: the task is not finished.
* **Built**: code or design exists, but the job has not passed all tests.
* **Blocked**: a documented dependency prevents completion.
* **Verified**: objective acceptance criterion met, evidence retained,
  an identified reviewer signed off with a date.

Never infer Verified from source existence or a passing generic CI run.

### Highest priority: blockers before beta

1. Recover the Windows installation after the failed 14% update.
   Identify whether that percentage was Git pull, dependency installation or
   the signed update UI; capture exact log, preserve all private user data.
2. Demonstrate interrupted/failed-update restart and rollback on real Windows
   hardware (R06-R13), including free-space and power interruption simulation.
3. Audit public Git history for tracked voice recordings, DBs, keys, tokens
   and other private runtime data (R03). Ignore rules alone do not undo an
   old commit. Do not rewrite history or delete data without owner approval.
4. Confirm Windows XTTS output, start/stop, timeout and GPU recovery (V01-V05).
5. Confirm real USB camera capture, imported image analysis and permission
   denial (V06-V10) rather than relying solely on mocked tests.
6. Exercise Research -> evidence note -> sourced Chat answer ->
   self-review -> approved proposal on the actual local LLM (L01-L15).
7. Prove limited, isolated, human-approved coding-team iteration (A01-A14).
8. Verify Pi on the real ARM hardware, not just a hosted runner (F01).
9. Publish only an owner-authorised Ed25519-signed test release, retaining
   a known-good offline recovery route and pinned public key.

## Machine-readable release sign-off

`docs/architecture/beta_status.json` intentionally begins empty: no
per-task verification has been fabricated. Update it one goal at a time:

```json
{
  "schema_version": 1,
  "goals": {
    "U05": {
      "status": "verified",
      "method": "manual",
      "evidence": "Local Windows session: voice select/retrain/delete; issue #...",
      "reviewed_by": "repository-owner",
      "reviewed_on": "2026-10-12"
    }
  }
}
```

Use evidence references or *non-sensitive* summaries; **never put private
recordings, medical data, device secrets, local log contents or key material
in this public JSON**. For hardware and security critical tasks the script
demands appropriate method labels, e.g. `real-windows`,
`fault-injection`, `real-camera`, `real-pi`, `privacy-review`,
`safety-review`, or `signed-release-dry-run`.

To view the current breakdown:

```bash
cd apollo_ui
python tools/beta_readiness.py
```

To attempt a release gate:

```bash
python tools/beta_readiness.py --gate beta
python tools/beta_readiness.py --gate stable
```

The beta/stable release workflow refuses promotion if any of the 86 goals
is unverified or evidence is incomplete. Stable is additionally blocked
unless the version is in the intended `1.x` release line. These checks
are traceability gates, **not proof** that arbitrary evidence is true.
The repo owner still needs to validate hardware, review the evidence,
approve the candidate, configure signing safely and initiate release.

## Current verified repository findings (2026-10-12)

* Code version: `8.0.0.0`, listed as a development candidate.
* Main-branch GitHub regression and Pi software checks passed on
  2026-10-11. No real local XTTS/camera/Pi result is implied.
* GitHub Releases contains an earlier test prerelease with no signed assets,
  not a supported Apollo 8 beta.
* The normal updater exists, but the reported user's 14% failure has not
  been diagnosed or reproduced.
* Previously committed private runtime files require repository-history
  audit and careful remediation before public distribution.

**Beta exit:** all 86 criteria evidenced, risk items reviewed, signed update
trial and rollback successful, owner explicitly approves an 8.x beta.
**Apollo 1.0 exit:** finished roadmap, fresh regression, real-hardware
sign-off and explicit version-migration plan followed by stable release.
