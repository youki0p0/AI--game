---
name: jen-longrun
description: Long-running Jen PMO autonomous development loop. Use when the user wants Claude Code to keep working toward completion with checkpoints, quality gates, repair, and handoff.
disable-model-invocation: true
argument-hint: "<goal and constraints>"
---

# Jen Longrun

Use Jen PMO long-running cycle.

1. Create/update `.jen/mission.md` with Goal, Non-goals, Constraints, AC, Human Gates.
2. Create/update `.jen/tasks.json`.
3. Work in small cycles.
4. Delegate implementation to specialists.
5. Run quality gates.
6. Repair failures up to 3 loops.
7. Update `.jen/handoff.md` after each cycle.
8. Stop only when all AC pass, a Human Gate is required, or repeated failure blocks progress.

Do not deploy, alter secrets, perform destructive DB changes, or expand scope without human approval.
