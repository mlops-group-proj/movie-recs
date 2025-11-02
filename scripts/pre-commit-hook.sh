#!/usr/bin/env bash
# Pre-commit hook for quality gate validation
# Install: cp scripts/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -e

echo "🔍 Running pre-commit quality gates..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Run quality gates
if python scripts/quality_gate.py; then
    echo -e "${GREEN}✓ All quality gates passed${NC}"
    exit 0
else
    echo -e "${RED}✗ Quality gates failed${NC}"
    echo -e "${YELLOW}Fix the issues above or use 'git commit --no-verify' to bypass (not recommended)${NC}"
    exit 1
fi
