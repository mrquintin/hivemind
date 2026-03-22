#!/bin/bash
# Hivemind Client App Launcher
# Includes: target cleanup on build failure, expedited startup, loading screen

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENT_DIR="$ROOT_DIR/client"
MARKER="$CLIENT_DIR/.hivemind_installed"
TARGET_DIR="$CLIENT_DIR/src-tauri/target"

# Show native macOS notification instead of tkinter splash (avoids crash on machines without python-tk)
osascript -e 'display notification "Starting client..." with title "Hivemind Client"' 2>/dev/null || true

echo ''
echo '╔══════════════════════════════════════════════════════════════════╗'
echo '║           HIVEMIND CLIENT APP LAUNCHER                          ║'
echo '╚══════════════════════════════════════════════════════════════════╝'
echo ''

cd "$CLIENT_DIR" || { echo "ERROR: client/ folder not found"; exit 1; }

ensure_prereqs() {
    if ! command -v node &> /dev/null; then
        [ -n "$(command -v brew)" ] && brew install node || { echo '   ERROR: Install Node.js from https://nodejs.org/'; exit 1; }
    fi

    if ! command -v cargo &> /dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
    fi
}

ensure_prereqs

# Expedited: skip heavy cache clears on repeat runs
if [ -f "$MARKER" ]; then
    echo '   Using existing setup.'
    echo ''
    # Ensure tauri binary exists even on repeat runs (archived copies may lack node_modules)
    if [ ! -f node_modules/.bin/tauri ]; then
        echo '   Dependencies missing — reinstalling...'
        npm install --prefer-offline --no-audit --no-fund 2>/dev/null || npm install
        echo ''
    fi
else
    echo '   First run — installing prerequisites...'
    echo ''
    rm -rf node_modules/.cache node_modules/.vite 2>/dev/null

    npm install --prefer-offline --no-audit --no-fund 2>/dev/null || npm install
    date > "$MARKER"
    echo '   First-time setup complete.'
    echo ''
fi

echo '   Starting Client App...'
echo '   (Loading screen will close when ready)'
echo ''
echo '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
echo ''

# Run with retry on build failure
run_tauri() {
    ./node_modules/.bin/tauri dev
}

TAURI_OUTPUT=$(mktemp)
if ! run_tauri 2>&1 | tee "$TAURI_OUTPUT"; then
    EXIT=${PIPESTATUS[0]:-1}
    if grep -q "failed to link or copy\|No such file or directory" "$TAURI_OUTPUT" 2>/dev/null; then
        echo ''
        echo '   Build cache corrupted — clearing and retrying...'
        rm -rf "$TARGET_DIR"
        if ! run_tauri; then
            exit $?
        fi
    else
        exit $EXIT
    fi
fi
rm -f "$TAURI_OUTPUT"
