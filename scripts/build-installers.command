#!/bin/bash
# =============================================================================
# Hivemind — Build .pkg Installers and Uninstallers
# =============================================================================
# Creates macOS .pkg installers for both Admin and Client apps by:
#   1. Running Tauri release builds (compiles native macOS .app + .dmg)
#   2. Extracting the .app from the Tauri-generated DMG
#   3. Packaging each .app into a .pkg installer via pkgbuild
#   4. Creating uninstaller scripts for each app
#
# Output goes to: build/installers/
#   Hivemind-Admin-Installer.pkg
#   Hivemind-Client-Installer.pkg
#   Uninstall-Hivemind-Admin.command
#   Uninstall-Hivemind-Client.command
#
# Prerequisites: Node.js, Rust/Cargo, Xcode Command Line Tools
# =============================================================================

set -uo pipefail
# NOTE: Not using set -e because we handle errors explicitly per-step.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/installers"
ADMIN_DIR="$ROOT_DIR/admin"
CLIENT_DIR="$ROOT_DIR/client"
VERSION="0.1.0"

echo ''
echo '╔══════════════════════════════════════════════════════════════════╗'
echo '║           HIVEMIND — BUILD INSTALLERS                           ║'
echo '╚══════════════════════════════════════════════════════════════════╝'
echo ''

# ─────────────────────────────────────────────────────────────────────
# Preflight checks
# ─────────────────────────────────────────────────────────────────────

FAILED=0
for cmd_info in \
    "node|Install from https://nodejs.org/" \
    "cargo|Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" \
    "pkgbuild|Install Xcode Command Line Tools: xcode-select --install" \
    "hdiutil|Built into macOS — are you running on macOS?"; do
    cmd="${cmd_info%%|*}"
    hint="${cmd_info#*|}"
    if ! command -v "$cmd" &>/dev/null; then
        echo "   ERROR: $cmd is required but not found."
        echo "          $hint"
        FAILED=1
    fi
done
if [ "$FAILED" -eq 1 ]; then
    echo ''
    echo '   Aborting — fix the above and re-run.'
    exit 1
fi

echo '   Prerequisites OK (node, cargo, pkgbuild, hdiutil)'
echo ''

# ─────────────────────────────────────────────────────────────────────
# Prepare output directory
# ─────────────────────────────────────────────────────────────────────

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# ─────────────────────────────────────────────────────────────────────
# Build function
# ─────────────────────────────────────────────────────────────────────

build_app() {
    local APP_NAME="$1"      # "admin" or "client"
    local APP_DIR="$2"       # full path to app directory
    local PRODUCT_NAME="$3"  # "Hivemind Admin" or "Hivemind Client"
    local IDENTIFIER="$4"    # e.g. com.thenashlab.hivemind.admin
    local PKG_NAME="$5"      # e.g. Hivemind-Admin-Installer.pkg

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "   Building $PRODUCT_NAME..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ''

    cd "$APP_DIR" || { echo "   ERROR: cannot cd to $APP_DIR"; return 1; }

    # Ensure npm dependencies are installed
    if [ ! -d node_modules ] || [ ! -f node_modules/.bin/tauri ]; then
        echo "   Installing npm dependencies..."
        npm install --prefer-offline --no-audit --no-fund 2>/dev/null || npm install
        echo ''
    fi

    # Run Tauri release build — capture full output for debugging on failure
    echo "   Compiling native macOS app (this may take several minutes)..."
    echo ''

    local BUILD_LOG="$BUILD_DIR/${APP_NAME}-build.log"
    if npm run tauri build > "$BUILD_LOG" 2>&1; then
        echo "   Tauri build succeeded."
    else
        echo "   ERROR: Tauri build failed for $PRODUCT_NAME."
        echo "   Last 30 lines of build log:"
        echo ''
        tail -30 "$BUILD_LOG" | sed 's/^/      /'
        echo ''
        echo "   Full log: $BUILD_LOG"
        return 1
    fi
    echo ''

    # Find the generated DMG
    local DMG_DIR="$APP_DIR/src-tauri/target/release/bundle/dmg"
    local DMG_FILE=""

    if [ -d "$DMG_DIR" ]; then
        # Find the most recently modified .dmg file (Tauri names it based on productName)
        DMG_FILE=$(find "$DMG_DIR" -maxdepth 1 -name "*.dmg" -type f -newer "$BUILD_LOG" 2>/dev/null | head -1)
        # Fallback: just pick the newest .dmg if none is newer than the log
        if [ -z "$DMG_FILE" ]; then
            DMG_FILE=$(ls -t "$DMG_DIR"/*.dmg 2>/dev/null | head -1)
        fi
    fi

    if [ -z "$DMG_FILE" ] || [ ! -f "$DMG_FILE" ]; then
        echo "   ERROR: No .dmg found in $DMG_DIR after build."
        echo "   Contents of bundle directory:"
        ls -la "$APP_DIR/src-tauri/target/release/bundle/" 2>&1 | sed 's/^/      /'
        return 1
    fi

    echo "   DMG found: $(basename "$DMG_FILE")"

    # Mount the DMG and extract the .app
    local MOUNT_POINT
    MOUNT_POINT=$(mktemp -d /tmp/hivemind-dmg-XXXXXX)
    if [ ! -d "$MOUNT_POINT" ]; then
        echo "   ERROR: Failed to create temp directory."
        return 1
    fi

    # Ensure DMG is always unmounted on exit/interrupt from this function
    _cleanup_dmg() { hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true; rm -rf "$MOUNT_POINT"; }
    trap _cleanup_dmg EXIT INT TERM

    echo "   Mounting DMG to extract .app..."
    if ! hdiutil attach "$DMG_FILE" -mountpoint "$MOUNT_POINT" -nobrowse -quiet 2>&1; then
        echo "   ERROR: Failed to mount DMG: $DMG_FILE"
        trap - EXIT INT TERM
        rm -rf "$MOUNT_POINT"
        return 1
    fi

    # Find the .app inside the mounted DMG
    local APP_BUNDLE
    APP_BUNDLE=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" -type d | head -1)

    if [ -z "$APP_BUNDLE" ] || [ ! -d "$APP_BUNDLE" ]; then
        echo "   ERROR: No .app found inside mounted DMG."
        echo "   DMG contents:"
        ls -la "$MOUNT_POINT" 2>&1 | sed 's/^/      /'
        _cleanup_dmg
        trap - EXIT INT TERM
        return 1
    fi

    echo "   Found: $(basename "$APP_BUNDLE")"

    # Stage the .app for pkgbuild
    local STAGE_DIR="$BUILD_DIR/stage-${APP_NAME}"
    rm -rf "$STAGE_DIR"
    mkdir -p "$STAGE_DIR/Applications"

    echo "   Copying .app to staging area..."
    cp -RP "$APP_BUNDLE" "$STAGE_DIR/Applications/$PRODUCT_NAME.app"

    # Unmount the DMG immediately — we have our copy
    _cleanup_dmg
    trap - EXIT INT TERM

    # Ad-hoc sign the staged .app
    echo "   Signing $PRODUCT_NAME.app..."
    codesign --force --deep --sign - "$STAGE_DIR/Applications/$PRODUCT_NAME.app" 2>/dev/null || {
        echo "   WARNING: Ad-hoc signing failed (non-fatal — app may trigger Gatekeeper)."
    }

    # Build the .pkg installer
    echo "   Creating $PKG_NAME..."
    if ! pkgbuild \
        --root "$STAGE_DIR" \
        --identifier "$IDENTIFIER" \
        --version "$VERSION" \
        --install-location "/" \
        "$BUILD_DIR/$PKG_NAME" 2>&1; then
        echo "   ERROR: pkgbuild failed."
        rm -rf "$STAGE_DIR"
        return 1
    fi

    # Verify the .pkg was actually created
    if [ ! -f "$BUILD_DIR/$PKG_NAME" ]; then
        echo "   ERROR: $PKG_NAME was not created."
        rm -rf "$STAGE_DIR"
        return 1
    fi

    local PKG_SIZE
    PKG_SIZE=$(ls -lh "$BUILD_DIR/$PKG_NAME" | awk '{print $5}')
    echo "   $PKG_NAME created ($PKG_SIZE)."

    # Clean up staging
    rm -rf "$STAGE_DIR"

    echo ''
}

# ─────────────────────────────────────────────────────────────────────
# Build uninstaller function
# ─────────────────────────────────────────────────────────────────────

create_uninstaller() {
    local PRODUCT_NAME="$1"    # "Hivemind Admin" or "Hivemind Client"
    local IDENTIFIER="$2"     # e.g. com.thenashlab.hivemind.admin
    local UNINSTALL_FILE="$3" # e.g. Uninstall-Hivemind-Admin.command

    local OUTFILE="$BUILD_DIR/$UNINSTALL_FILE"

    # Write the uninstaller script — use a quoted heredoc so nothing is expanded
    cat > "$OUTFILE" << 'ENDOFSCRIPT'
#!/bin/bash
# =============================================================================
# Hivemind Uninstaller
# =============================================================================
ENDOFSCRIPT

    # Now append the parts that need variable expansion (at generation time)
    cat >> "$OUTFILE" << ENDOFVARS
APP_PATH="/Applications/${PRODUCT_NAME}.app"
PKG_ID="${IDENTIFIER}"
DISPLAY_NAME="${PRODUCT_NAME}"
ENDOFVARS

    # Append the rest with no expansion (runtime variables)
    cat >> "$OUTFILE" << 'ENDOFSCRIPT'

echo ''
echo '============================================================'
echo "   Hivemind Uninstaller"
echo '============================================================'
echo ''
echo "   This will remove $DISPLAY_NAME from your computer."
echo ''
printf "   Are you sure? (y/N) "
read -r REPLY
echo ''

if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo '   Cancelled. Nothing was removed.'
    echo ''
    exit 0
fi

# Remove the application — needs sudo for /Applications
if [ -d "$APP_PATH" ]; then
    echo "   Removing $APP_PATH..."
    if rm -rf "$APP_PATH" 2>/dev/null; then
        echo '   Application removed.'
    else
        echo '   Need administrator privileges to remove from /Applications...'
        sudo rm -rf "$APP_PATH"
        echo '   Application removed.'
    fi
else
    echo "   $APP_PATH not found (already removed?)."
fi

# Forget the installer receipt
if pkgutil --pkgs 2>/dev/null | grep -q "$PKG_ID"; then
    echo "   Removing installer receipt..."
    sudo pkgutil --forget "$PKG_ID" 2>/dev/null || true
    echo '   Receipt removed.'
fi

echo ''
echo '============================================================'
echo "   $DISPLAY_NAME has been uninstalled."
echo '============================================================'
echo ''
ENDOFSCRIPT

    chmod +x "$OUTFILE"
    echo "   Created $UNINSTALL_FILE"
}

# ─────────────────────────────────────────────────────────────────────
# Build both apps
# ─────────────────────────────────────────────────────────────────────

ERRORS=0

build_app "admin" "$ADMIN_DIR" "Hivemind Admin" \
    "com.thenashlab.hivemind.admin" "Hivemind-Admin-Installer.pkg" || ERRORS=$((ERRORS + 1))

build_app "client" "$CLIENT_DIR" "Hivemind Client" \
    "com.thenashlab.hivemind.client" "Hivemind-Client-Installer.pkg" || ERRORS=$((ERRORS + 1))

# ─────────────────────────────────────────────────────────────────────
# Create uninstallers
# ─────────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo '   Creating uninstallers...'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ''

create_uninstaller "Hivemind Admin" \
    "com.thenashlab.hivemind.admin" "Uninstall-Hivemind-Admin.command"

create_uninstaller "Hivemind Client" \
    "com.thenashlab.hivemind.client" "Uninstall-Hivemind-Client.command"

# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────

echo ''

if [ "$ERRORS" -gt 0 ]; then
    echo '╔══════════════════════════════════════════════════════════════════╗'
    echo '║           BUILD COMPLETED WITH ERRORS                           ║'
    echo '╚══════════════════════════════════════════════════════════════════╝'
    echo ''
    echo "   $ERRORS app(s) failed to build. Check the logs above."
    echo "   Build logs saved to: $BUILD_DIR/"
    echo ''
    exit 1
fi

echo '╔══════════════════════════════════════════════════════════════════╗'
echo '║           BUILD COMPLETE                                        ║'
echo '╚══════════════════════════════════════════════════════════════════╝'
echo ''
echo '   Output directory: build/installers/'
echo ''
ls -lh "$BUILD_DIR"/*.pkg "$BUILD_DIR"/*.command 2>/dev/null | awk '{printf "      %-45s %s\n", $NF, $5}'
echo ''
echo '   To install: double-click the .pkg file'
echo '   To uninstall: double-click the .command file'
echo ''
