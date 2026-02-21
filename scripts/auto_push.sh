#!/bin/zsh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Skip if git metadata is not present.
if [[ ! -d .git ]]; then
  exit 0
fi

# Avoid overlapping runs.
LOCK_DIR=".git/.auto_push_lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" >/dev/null 2>&1 || true' EXIT

# Skip if repository is in the middle of merge/rebase/cherry-pick.
if [[ -f .git/MERGE_HEAD || -f .git/CHERRY_PICK_HEAD || -d .git/rebase-apply || -d .git/rebase-merge ]]; then
  exit 0
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# Commit and push only when there are local working-tree changes.
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A

  if [[ -n "$(git diff --cached --name-only)" ]]; then
    COMMIT_MSG="auto: sync local changes $(date '+%Y-%m-%d %H:%M:%S %Z')"
    git commit -m "$COMMIT_MSG"

    # Handle non-fast-forward by rebasing once, then push.
    if ! git push origin "$CURRENT_BRANCH"; then
      git pull --rebase --autostash origin "$CURRENT_BRANCH"
      git push origin "$CURRENT_BRANCH"
    fi
  fi
fi

exit 0