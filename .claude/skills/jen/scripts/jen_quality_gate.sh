#!/usr/bin/env bash
set -euo pipefail

mkdir -p .jen/reports
REPORT=".jen/reports/quality-gate-$(date -u +%Y%m%dT%H%M%SZ).md"

echo "# Jen Quality Gate" > "$REPORT"
echo "" >> "$REPORT"
echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$REPORT"
echo "" >> "$REPORT"

run_step() {
  name="$1"
  shift
  echo "## $name" >> "$REPORT"
  echo '```' >> "$REPORT"
  if "$@" >> "$REPORT" 2>&1; then
    echo '```' >> "$REPORT"
    echo "PASS: $name"
    echo "PASS" >> "$REPORT"
  else
    code=$?
    echo '```' >> "$REPORT"
    echo "FAIL: $name (exit $code)"
    echo "FAIL exit $code" >> "$REPORT"
    exit "$code"
  fi
  echo "" >> "$REPORT"
}

run_step "git diff check" git diff --check

if [ -f package.json ]; then
  if command -v node >/dev/null 2>&1; then
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.lint?0:1)"; then
      run_step "npm lint" npm run lint --if-present
    fi
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.typecheck?0:1)"; then
      run_step "npm typecheck" npm run typecheck --if-present
    fi
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.test?0:1)"; then
      run_step "npm test" npm test -- --runInBand
    fi
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.build?0:1)"; then
      run_step "npm build" npm run build --if-present
    fi
  fi
fi

if [ -f pyproject.toml ] || [ -d tests ]; then
  if command -v pytest >/dev/null 2>&1; then
    run_step "pytest" pytest -q
  fi
fi

if [ -f go.mod ]; then
  run_step "go test" go test ./...
fi

if [ -f Cargo.toml ]; then
  run_step "cargo test" cargo test
fi

echo "Quality gate report: $REPORT"
