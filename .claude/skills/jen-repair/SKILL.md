---
name: jen-repair
description: Jen repair mode for failing tests, broken builds, runtime crashes, verifier rejection, or regressions.
disable-model-invocation: true
argument-hint: "<failure evidence>"
---

# Jen Repair

1. Fix the reproduction command or steps.
2. Classify the failure.
3. Use `jen-debugger` for unknown/root-cause work or `jen-test` for test-specific failures.
4. Apply minimal fix.
5. Add regression test if possible.
6. Run relevant quality gate.
7. Use `jen-verifier` or `jen-strict-verifier` for acceptance.
8. Record failure and fix in `.jen/verification.md` and `.jen/handoff.md`.
