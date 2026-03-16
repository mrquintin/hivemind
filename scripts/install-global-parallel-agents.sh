#!/usr/bin/env bash
# Install Parallel Agent rules from this project for use in all Cursor projects
# or into another project directory.
#
# Usage:
#   ./scripts/install-global-parallel-agents.sh
#     → Writes a rules file you can paste into Cursor Settings → Rules for AI (global).
#   ./scripts/install-global-parallel-agents.sh /path/to/other/project
#     → Copies .cursorrules (and optional worktrees/settings) into that project.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RULES_SOURCE="$PROJECT_ROOT/.cursorrules"
WORKTREES_SOURCE="$PROJECT_ROOT/.cursor/worktrees.json"
GLOBAL_RULES_OUTPUT="$HOME/cursor-parallel-agents-rules.txt"

usage() {
  echo "Usage:"
  echo "  $0                    Write rules to $GLOBAL_RULES_OUTPUT for pasting into Cursor → Settings → Rules for AI"
  echo "  $0 <project-path>     Copy .cursorrules (and optional config) into <project-path>"
  echo ""
  echo "To apply to ALL Cursor projects: run with no args, then paste the output file into Cursor Settings → General → Rules for AI."
  echo "To apply to ONE project: run with the project path (e.g. $0 ~/my-app)."
}

install_into_project() {
  local dest_root="$1"
  if [[ ! -d "$dest_root" ]]; then
    echo "Error: Not a directory: $dest_root"
    exit 1
  fi
  if [[ ! -f "$RULES_SOURCE" ]]; then
    echo "Error: Source rules not found: $RULES_SOURCE"
    exit 1
  fi
  echo "Installing parallel agent rules into: $dest_root"
  cp "$RULES_SOURCE" "$dest_root/.cursorrules"
  echo "  → .cursorrules"
  if [[ -f "$WORKTREES_SOURCE" ]]; then
    mkdir -p "$dest_root/.cursor"
    cp "$WORKTREES_SOURCE" "$dest_root/.cursor/worktrees.json"
    echo "  → .cursor/worktrees.json"
  fi
  echo "Done. Open $dest_root in Cursor to use the rules."
}

write_global_paste_file() {
  if [[ ! -f "$RULES_SOURCE" ]]; then
    echo "Error: Source rules not found: $RULES_SOURCE"
    exit 1
  fi
  cp "$RULES_SOURCE" "$GLOBAL_RULES_OUTPUT"
  echo "Wrote: $GLOBAL_RULES_OUTPUT"
  echo ""
  echo "To use these rules in ALL Cursor projects:"
  echo "  1. Open Cursor → Settings (Cmd+,) → Cursor Settings → General"
  echo "  2. Find 'Rules for AI'"
  echo "  3. Open the file below and paste its contents into Rules for AI:"
  echo "     $GLOBAL_RULES_OUTPUT"
  echo ""
  echo "To open the file now: open \"$GLOBAL_RULES_OUTPUT\""
}

if [[ $# -eq 0 ]]; then
  write_global_paste_file
elif [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
else
  install_into_project "$1"
fi
