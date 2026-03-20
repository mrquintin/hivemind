#!/bin/sh
# Get off GitButler and into a state where the sync script works.
# Run this once if GitButler is blocking commits or you see "branch has no commits".
set -e
cd "$(git rev-parse --show-toplevel)"

# Remove GitButler's pre-commit hook so normal git commit works
if [ -f ".git/hooks/pre-commit" ] && grep -q GITBUTLER_MANAGED_HOOK ".git/hooks/pre-commit" 2>/dev/null; then
  rm ".git/hooks/pre-commit"
  echo "Removed GitButler pre-commit hook."
fi

# Switch to main (repo already has commits; we just need to be on main)
git checkout main
echo "On branch main."

echo ""
echo "Done. Use the 'Sync to GitHub (after Keep all)' task or run: ./scripts/sync-to-github.sh"
echo ""
