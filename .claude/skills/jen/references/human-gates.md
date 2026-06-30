# Human Gates

Stop and ask for human approval before:

- production deploy
- database destructive migration
- auth/authorization/payment changes
- secret/env changes
- external paid service setup
- public API breaking changes
- legal/terms/pricing decisions
- deleting data or files outside scoped work
- force push, reset hard, publish
- large refactor not required by AC

Output a decision packet:

```md
## Human Gate
Decision needed: ...
Options:
1. ... risk/benefit
2. ... risk/benefit
Recommended: ...
Safe default: ...
```
