# Long-run Playbook

## Cycle

1. Read `.jen/mission.md` and `.jen/tasks.json`.
2. Pick one small unblocked task.
3. Delegate to the correct specialist.
4. Run relevant quality gate.
5. If pass, update ledger and handoff.
6. If fail, invoke repair.
7. If human gate appears, stop with a clear packet.

## Drift control

- Every task must map to AC.
- Side ideas go to `.jen/ideas.md`.
- Do not expand scope silently.
- Keep changes small.
- Write handoff after each cycle.

## Checkpoint

```bash
git status --short
git diff --stat
bash .claude/skills/jen/scripts/jen_quality_gate.sh
```

## Stop conditions

- All AC pass.
- Human Gate needed.
- Same failure repeats 3 times.
- Required external secret/service missing.
- Risk is higher than allowed constraints.
