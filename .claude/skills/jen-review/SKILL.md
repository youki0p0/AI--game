---
name: jen-review
description: Jen review mode for acceptance review, UX/product/security/contrarian review, and PR readiness checks.
disable-model-invocation: true
argument-hint: "<target diff or feature>"
---

# Jen Review

Run only the reviewers needed for the risk profile:

- product-strategist for scope/value
- ux-critic for UI/user flows
- security-reviewer for auth/payment/secret/input/data
- contrarian-reviewer for hidden failure modes
- monetization-reviewer for pricing/business implications
- verifier for AC acceptance
- strict-verifier for high risk

Output ACCEPT/REJECT, evidence, unresolved risks, and next owner.
