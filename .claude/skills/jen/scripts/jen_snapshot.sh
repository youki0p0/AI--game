#!/usr/bin/env bash
set -euo pipefail
mkdir -p .jen/checkpoints
OUT=".jen/checkpoints/snapshot-$(date -u +%Y%m%dT%H%M%SZ).md"
{
  echo "# Jen Snapshot"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## git status"
  echo '```'
  git status --short || true
  echo '```'
  echo
  echo "## git diff stat"
  echo '```'
  git diff --stat || true
  echo '```'
  echo
  echo "## recent verification"
  if [ -f .jen/verification.md ]; then tail -n 80 .jen/verification.md; else echo "No verification file"; fi
} > "$OUT"
echo "$OUT"
