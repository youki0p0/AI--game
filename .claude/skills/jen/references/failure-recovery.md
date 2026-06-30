# Failure Recovery

## Classification

- build failure
- lint failure
- type failure
- unit test failure
- e2e failure
- runtime crash
- flaky test
- spec ambiguity
- environment missing
- unknown

## Loop

1. Reproduce
2. Classify
3. Identify likely cause
4. Minimal fix
5. Add/adjust test if appropriate
6. Verify
7. Record

Max 3 loops per same failure. After that, escalate to debugger/architect or Human Gate.
