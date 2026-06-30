# Source Integrity

## Trust order

1. Official docs
2. Official repo/release notes/changelog
3. Standards/RFC/spec
4. Source code
5. Maintainer discussion
6. Reputable technical article
7. Q&A/forum/blog

## Required separation

- Confirmed: source or code verified
- Unconfirmed: plausible but not verified
- Assumption: reversible decision made to proceed

## External API rule

Do not implement against external API/library behavior until version and source are checked.
If version is unknown, inspect package files or mark as unconfirmed.
