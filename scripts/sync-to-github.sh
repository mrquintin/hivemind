#!/bin/sh
# Commit all current changes and push to GitHub.
# Run this after Cursor's "Keep all" to update https://github.com/mrquintin/hivemind
set -e
cd "$(git rev-parse --show-toplevel)"
# Use --show-current so we have a branch name even with no commits yet (unborn branch)
branch=$(git branch --show-current 2>/dev/null) || branch=main

# If we're on GitButler's branch, switch to main and remove its hook so we can commit.
if [ "$branch" = "gitbutler/workspace" ]; then
  [ -f ".git/hooks/pre-commit" ] && grep -q GITBUTLER_MANAGED_HOOK ".git/hooks/pre-commit" 2>/dev/null && rm ".git/hooks/pre-commit"
  need_stash_pop=0
  if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    if git stash push -m "sync: before checkout main" 2>/dev/null; then
      need_stash_pop=1
    else
      # Stash failed (e.g. "no initial commit yet") - commit here, then bring into main and push
      git add -A
      git commit -m "Sync: Cursor edits"
      git fetch origin 2>/dev/null || true
      if git rev-parse --verify origin/main >/dev/null 2>&1; then
        git checkout -B main origin/main
        git merge gitbutler/workspace -m "Merge Cursor edits"
      else
        git checkout -B main
      fi
      git push origin main
      echo "Pushed to origin/main"
      exit 0
    fi
  fi
  git checkout main 2>/dev/null || git fetch origin && git checkout -B main origin/main
  [ "$need_stash_pop" = 1 ] && git stash pop
  branch=main
fi

git add -A
# Use status --porcelain so we don't need HEAD (works with no commits yet)
if ! git status --porcelain | grep -q '^[MADRCU]'; then
  echo "Nothing to commit."
  exit 0
fi
git commit -m "Sync: Cursor edits"
git push origin "$branch"
echo "Pushed to origin/$branch"
