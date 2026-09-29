Apollo 7.5.12.4 — Fleet + Cluster Foundation + Personal Voice Mode

Install over 7.5.12.3 with Apollo completely closed.

FIRST CLUSTER TEST
------------------
On each sub-node:
1. Open Apps -> Apollo Device Agent.
2. Give it a device name/role/group.
3. Start Agent.
4. Copy Enrollment Token.

On the main Apollo:
1. Open Apps -> Apollo Fleet Manager.
2. Enter the sub-node URL, usually http://DEVICE-IP:8766, and the token.
3. Enrol and Refresh Fleet.
4. Open Cluster Manager and run independent subtasks.

Voice Imprint Lab is now in personal-use mode and no longer blocks import/train/activation/synthesis on a rights-confirmation checkbox.

This release does not yet remotely push updates to the whole fleet; Fleet Rollout Controller is the next distributed-update layer.
