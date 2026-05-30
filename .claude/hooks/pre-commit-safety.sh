#!/usr/bin/env bash
# Scholara pre-commit safety gate
# Blocks commits that include sensitive files.

BLOCKED=$(git diff --cached --name-only | grep -E \
  '\.(env|key|pem|p12|pfx)$|^\.env$|\.env\.|scholara\.db$|adm_app\.db$|secrets\.(json|yml|yaml)$|creds\.')

if [ -n "$BLOCKED" ]; then
  echo ""
  echo "BLOCKED: attempt to commit sensitive files:"
  echo "$BLOCKED" | sed 's/^/  /'
  echo ""
  echo "If this is intentional, use: git commit --no-verify"
  exit 1
fi
