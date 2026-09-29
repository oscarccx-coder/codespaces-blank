# Apollo Fleet + Cluster Foundation

## Roles
- Coordinator: plans/integrates tasks.
- Worker: executes assigned allow-listed tasks.
- Hybrid: can coordinate and work.

## Trust
Each Device Agent creates a per-node enrollment token. Fleet requests are timestamped HMAC-SHA256 signed and replay-protected. Identity is visible for enrolment; status/tasks require authentication.

## Current distributed tasks
The 7.5.12.4 worker intentionally exposes only a small safe contract: ping, SHA-256 text, JSON validation, Python syntax validation, workspace file hashing and local Ollama prompt subtasks. There is no remote command shell.

## Next layers
7.5.12.5 Fleet Rollout Controller -> 7.5.12.6 Distributed Project Snapshots -> 7.5.12.7 Worker leases/reassignment/verification -> 7.5.12.8 Development Missions + Cluster DAG execution.
