# Quality Gates

## Required gates

| Gate | When | Owner |
|---|---|---|
| Scope | before work | jen-pmo |
| Source | external info | jen-research |
| Build | code change | jen-builder/frontend/test |
| Lint | code change | jen-builder/frontend/test |
| Typecheck | TS/Python typed project | jen-builder/frontend/test |
| Unit test | logic change | jen-test |
| E2E/manual | user flow/UI | jen-ux-critic + jen-verifier |
| Security | auth/payment/secret/data | jen-security-reviewer |
| Strict verify | high risk | jen-strict-verifier |
| Release | PR/deploy prep | jen-release-manager |

## Evidence rule

Verifier must cite commands, files, screenshots/manual steps, or explicit unverified items.
No evidence means no ACCEPT.
