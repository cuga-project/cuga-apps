# Agent backends

The orchestrator only sees [`base.py`](base.py)'s `AgentClient` Protocol.

To swap cuga for another agent:

1. Create `gpt_oss_client.py` (or whatever) in this folder.
2. Implement `plan_and_execute`, `health`, `aclose`.
3. Wire it in `orchestrator.py`'s `_build_agent` based on the
   `CHIEF_OF_STAFF_AGENT` env var.

No other file in the repo should ever import a concrete client.
