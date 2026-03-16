#!/bin/bash
# ============================================================================
# Hivemind - First Run Setup
# ============================================================================
# RUN THIS ONCE on any new computer after transferring the HivemindSoftware
# folder. It removes macOS quarantine flags and signs all launcher apps so
# they open without passwords or security warnings.
#
# After running this, you should never need to run it again on this machine.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ''
echo '╔══════════════════════════════════════════════════════════════════╗'
echo '║           HIVEMIND - FIRST RUN SETUP                            ║'
echo '╚══════════════════════════════════════════════════════════════════╝'
echo ''
echo '   This removes macOS security restrictions so all'
echo '   Hivemind apps can launch without passwords.'
echo ''

cd "$SCRIPT_DIR"

# ============================================================================
# Step 1: Remove quarantine flags from everything
# ============================================================================

echo '   Removing quarantine flags...'
xattr -cr "$SCRIPT_DIR" 2>/dev/null
echo '   Done.'
echo ''

# ============================================================================
# Step 2: Make all scripts executable
# ============================================================================

echo '   Setting executable permissions...'

# .command scripts
chmod +x scripts/*.command 2>/dev/null
chmod +x "First Run Setup.command" 2>/dev/null

# .app executables
for app in *.app; do
    [ -d "$app" ] || continue
    exe="$app/Contents/MacOS/$(echo "$app" | sed 's/\.app$//')"
    if [ -f "$exe" ]; then
        chmod +x "$exe"
    fi
done

echo '   Done.'
echo ''

# ============================================================================
# Step 3: Ad-hoc code sign all .app bundles
# ============================================================================

echo '   Signing launcher apps...'

for app in *.app; do
    [ -d "$app" ] || continue
    codesign --force --sign - "$app" 2>/dev/null
    printf '     %s\n' "$app"
done

echo '   Done.'
echo ''

# ============================================================================
# Done
# ============================================================================

echo '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
echo ''
echo '   Setup complete! All apps should now open without'
echo '   passwords or security warnings.'
echo ''
echo '   You only need to run this once per computer.'
echo ''
echo '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
echo ''
