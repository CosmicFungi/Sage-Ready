#!/usr/bin/env bash
# Publish this Linux line to CosmicFungi/Sage-Ready (optional dedicated branch or main).
# Run on a machine logged into GitHub as CosmicFungi.
#
# Examples:
#   ./publish-to-sage-ready.sh              # force-push HEAD → main
#   ./publish-to-sage-ready.sh HEAD linux   # force-push HEAD → linux branch
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REMOTE_URL="${SAGE_READY_REMOTE:-https://github.com/CosmicFungi/Sage-Ready.git}"
SRC="${1:-HEAD}"
DEST="${2:-main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repo: $ROOT" >&2
  exit 1
fi

echo "Sage Ready Linux v1.34 — force-pushing $SRC → $REMOTE_URL ($DEST)…"
git push --force "$REMOTE_URL" "$SRC:$DEST"
echo "Done. Open https://github.com/CosmicFungi/Sage-Ready"
