#!/usr/bin/env bash
# Publish the current Sage Ready tree to CosmicFungi/Sage-Ready (main), overwriting.
# Run this on a machine logged into GitHub as CosmicFungi (gh auth / git credentials).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REMOTE_URL="${SAGE_READY_REMOTE:-https://github.com/CosmicFungi/Sage-Ready.git}"
BRANCH="${1:-HEAD}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repo: $ROOT" >&2
  exit 1
fi

echo "Force-pushing $BRANCH → $REMOTE_URL (main)…"
git push --force "$REMOTE_URL" "$BRANCH:main"
echo "Done. Open https://github.com/CosmicFungi/Sage-Ready"
