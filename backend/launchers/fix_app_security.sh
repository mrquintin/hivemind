#!/bin/bash
# =============================================================================
# Fix App Security - Remove Gatekeeper Prompts
# =============================================================================
# This script removes quarantine attributes and allows apps to run without
# Touch ID/password prompts.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

echo ""
echo "=============================================="
echo "   FIX APP SECURITY (GATEKEEPER)"
echo "=============================================="
echo ""
echo "This will remove security restrictions from all"
echo "Hivemind app bundles so they open without prompts."
echo ""

cd "$ROOT_DIR"

APPS=(
    "Cloud Setup.app"
    "Admin Setup.app"
    "Client Setup.app"
    "Cloud Stop.app"
    "Archive Cloud.app"
    "Archive Admin.app"
    "Archive Client.app"
    "Archive Hivemind.app"
)

log_step "Removing quarantine attributes..."
for app in "${APPS[@]}"; do
    if [ -d "$app" ]; then
        # Remove all extended attributes that might cause issues
        xattr -cr "$app" 2>/dev/null || true
        
        # Specifically remove quarantine if it exists
        xattr -d com.apple.quarantine "$app" 2>/dev/null || true
        
        # Remove FinderInfo
        xattr -d com.apple.FinderInfo "$app" 2>/dev/null || true
        
        # Remove ResourceFork
        xattr -d com.apple.ResourceFork "$app" 2>/dev/null || true
        
        log_info "✓ Cleaned $app"
    fi
done

log_step "Removing .DS_Store files..."
find . -name ".DS_Store" -type f -delete 2>/dev/null || true
log_info "✓ Removed .DS_Store files"

log_step "Attempting to sign apps (ad-hoc signature)..."
SIGNED_COUNT=0
FAILED_COUNT=0

for app in "${APPS[@]}"; do
    if [ -d "$app" ]; then
        # Try to sign with ad-hoc signature
        if codesign --force --deep --sign - "$app" 2>/dev/null; then
            log_info "✓ Signed $app"
            SIGNED_COUNT=$((SIGNED_COUNT + 1))
        else
            log_warn "✗ Could not sign $app (may have resource forks)"
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
    fi
done

echo ""
if [ $SIGNED_COUNT -gt 0 ]; then
    log_info "Successfully signed $SIGNED_COUNT app(s)"
fi

if [ $FAILED_COUNT -gt 0 ]; then
    log_warn "$FAILED_COUNT app(s) could not be signed"
    echo ""
    echo "For apps that couldn't be signed, you can:"
    echo "  1. Right-click the app → 'Open' (first time only)"
    echo "  2. Or run: xattr -cr \"AppName.app\""
    echo ""
fi

log_step "Adding Gatekeeper exceptions for each app..."
EXCEPTION_COUNT=0

for app in "${APPS[@]}"; do
    if [ -d "$app" ]; then
        APP_PATH="$ROOT_DIR/$app"
        
        # Try to add exception (requires admin password)
        if sudo spctl --add "$APP_PATH" 2>/dev/null; then
            log_info "✓ Added exception for $app"
            EXCEPTION_COUNT=$((EXCEPTION_COUNT + 1))
        else
            log_warn "✗ Could not add exception for $app (may require admin password)"
        fi
    fi
done

if [ $EXCEPTION_COUNT -eq 0 ]; then
    echo ""
    log_info "Gatekeeper exceptions require administrator access."
    echo ""
    echo "To fix manually (choose one):"
    echo ""
    echo "Option 1 - Right-click each app (easiest):"
    echo "  1. Right-click each app → 'Open'"
    echo "  2. Click 'Open' in the dialog (first time only)"
    echo "  3. App will be added to exceptions automatically"
    echo ""
    echo "Option 2 - Run this script with sudo:"
    echo "  sudo bash backend/launchers/fix_app_security.sh"
    echo ""
    echo "Option 3 - Temporarily disable Gatekeeper (less secure):"
    echo "  sudo spctl --master-disable"
    echo "  (Re-enable later with: sudo spctl --master-enable)"
    echo ""
else
    log_info "Successfully added exceptions for $EXCEPTION_COUNT app(s)"
fi

echo ""
echo "=============================================="
echo "   COMPLETE!"
echo "=============================================="
echo ""
echo "Apps should now open without security prompts."
echo ""
echo "If you still see prompts:"
echo "  1. Right-click the app → 'Open' (first time only)"
echo "  2. Or run: sudo spctl --master-disable"
echo ""
