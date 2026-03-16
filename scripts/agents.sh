#!/usr/bin/env bash
# Parallel Agent Worktree Utilities
# Source this file: source scripts/agents.sh

REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")

# Create worktrees for parallel agent branches
# Usage: agent-spawn branch1 branch2 branch3 ...
agent-spawn() {
  local current_branch=$(git rev-parse --abbrev-ref HEAD)
  echo "🚀 Spawning agent worktrees from branch: $current_branch"

  for branch in "$@"; do
    local slug=$(echo "$branch" | tr '/' '-')
    local worktree_path="../${REPO_NAME}-agent-${slug}"

    if git worktree list | grep -q "$worktree_path"; then
      echo "⚠️  Worktree already exists: $worktree_path"
      continue
    fi

    git worktree add -b "agent/${branch}" "$worktree_path" "$current_branch" 2>/dev/null || \
    git worktree add "$worktree_path" "agent/${branch}" 2>/dev/null

    echo "✅ Created: $worktree_path → agent/${branch}"

    # Run setup if worktrees.json exists
    if [ -f ".cursor/worktrees.json" ]; then
      echo "   Running worktree setup..."
      (cd "$worktree_path" && eval "$(cat .cursor/worktrees.json | grep -o '"[^"]*"' | head -n5 | tail -n3 | tr -d '"')" 2>/dev/null)
    fi
  done

  echo ""
  echo "📋 Active worktrees:"
  git worktree list
}

# Merge an agent branch back and clean up
# Usage: agent-merge branch-name
agent-merge() {
  local branch="agent/${1}"
  local slug=$(echo "$1" | tr '/' '-')
  local worktree_path="../${REPO_NAME}-agent-${slug}"

  echo "🔀 Merging ${branch} into $(git rev-parse --abbrev-ref HEAD)..."
  git merge --no-ff "$branch" -m "merge: agent/${1} parallel work"

  if [ $? -eq 0 ]; then
    echo "🧹 Cleaning up worktree..."
    git worktree remove "$worktree_path" --force 2>/dev/null
    git branch -d "$branch" 2>/dev/null
    echo "✅ Merged and cleaned: ${branch}"
  else
    echo "❌ Merge conflicts detected. Resolve manually, then run:"
    echo "   git worktree remove $worktree_path --force && git branch -d $branch"
  fi
}

# Merge ALL agent branches and clean up
agent-merge-all() {
  echo "🔀 Merging all agent branches..."
  for worktree in $(git worktree list --porcelain | grep "^branch refs/heads/agent/" | sed 's|branch refs/heads/||'); do
    local name="${worktree#agent/}"
    agent-merge "$name"
  done
}

# List all active agent worktrees
agent-list() {
  echo "📋 Active agent worktrees:"
  git worktree list | grep "agent/" || echo "   (none)"
}

# Remove all agent worktrees without merging
agent-clean() {
  echo "🧹 Removing all agent worktrees..."
  for worktree_path in $(git worktree list --porcelain | grep "^worktree " | grep "agent-" | sed 's/worktree //'); do
    git worktree remove "$worktree_path" --force 2>/dev/null
    echo "   Removed: $worktree_path"
  done
  # Clean up agent branches (portable: only run xargs when there are branches)
  local agent_branches=$(git branch | grep "agent/" || true)
  if [ -n "$agent_branches" ]; then
    echo "$agent_branches" | xargs git branch -D 2>/dev/null || true
  fi
  echo "✅ All agent worktrees cleaned."
}

# Remove Cursor-created worktrees (under ~/.cursor/worktrees/) to free slots and fix "too many changes"
# Run from repo root. Only run when you don't need any in-progress agent results.
agent-clean-cursor() {
  echo "🧹 Removing Cursor worktrees for this repo..."
  while read -r line; do
    local path=$(echo "$line" | awk '{print $1}')
    if [[ "$path" == *".cursor/worktrees"* ]]; then
      git worktree remove "$path" --force 2>/dev/null && echo "   Removed: $path" || echo "   Skip (in use?): $path"
    fi
  done < <(git worktree list --porcelain | grep "^worktree ")
  echo "✅ Done. Run 'git worktree list' to confirm."
}

echo "🤖 Agent utilities loaded. Commands: agent-spawn, agent-merge, agent-merge-all, agent-list, agent-clean, agent-clean-cursor"
