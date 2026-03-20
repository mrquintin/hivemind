#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Hivemind Client Setup
# =============================================================================
# Installs prerequisites and runs the Client app.
# Can connect to a cloud server running anywhere.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$HOME/.hivemind/launcher"
LOG_FILE="$LOG_DIR/client_setup.log"
CONFIG_FILE="$HOME/.hivemind/client_config"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

version_ge() {
  [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

# =============================================================================
# Non-interactive Git/Homebrew config
# =============================================================================

configure_noninteractive() {
  export GIT_TERMINAL_PROMPT=0
  export GIT_ASKPASS="/usr/bin/true"
  export SSH_ASKPASS="/usr/bin/true"
  export SSH_ASKPASS_REQUIRE=force
  export GIT_SSH_COMMAND="ssh -o BatchMode=yes"
  export GIT_CONFIG_GLOBAL=/dev/null
  export GIT_CONFIG_SYSTEM=/dev/null
  export GIT_CONFIG_COUNT=1
  export GIT_CONFIG_KEY_0=credential.helper
  export GIT_CONFIG_VALUE_0=""
  export HOMEBREW_NO_AUTO_UPDATE=1
  export HOMEBREW_NO_ANALYTICS=1
}

# =============================================================================
# Install Xcode Command Line Tools
# =============================================================================

ensure_xcode_clt() {
  log_step "Checking Xcode Command Line Tools..."
  
  if xcode-select -p &>/dev/null; then
    log_info "Xcode Command Line Tools already installed."
    return
  fi
  
  log_warn "Xcode Command Line Tools not found. Installing..."
  echo ""
  echo "A dialog box will appear asking to install the tools."
  echo "Click 'Install' and wait for it to complete."
  echo ""
  
  xcode-select --install 2>/dev/null || true
  
  # Wait for installation
  echo "Waiting for installation to complete..."
  while ! xcode-select -p &>/dev/null; do
    sleep 5
  done
  
  log_info "Xcode Command Line Tools installed."
}

# =============================================================================
# Install Homebrew
# =============================================================================

ensure_homebrew() {
  log_step "Checking Homebrew..."
  if ! command_exists brew; then
    log_warn "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi

  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi

  if ! command_exists brew; then
    log_error "Homebrew installation failed."
    exit 1
  fi
  
  log_info "Homebrew ready."
}

# =============================================================================
# Install Node.js
# =============================================================================

ensure_node() {
  log_step "Checking Node.js 18+..."
  local node_version
  node_version="$(node --version 2>/dev/null || true)"

  if [ -z "$node_version" ]; then
    log_warn "Node.js not found. Installing..."
    brew install node@18
    export PATH="$(brew --prefix node@18)/bin:$PATH"
  else
    node_version="${node_version#v}"
    if ! version_ge "$node_version" "18.0"; then
      log_warn "Node.js $node_version too old. Installing node@18..."
      brew install node@18
      export PATH="$(brew --prefix node@18)/bin:$PATH"
    fi
  fi

  log_info "Node.js ready."
}

# =============================================================================
# Install Rust
# =============================================================================

ensure_rust() {
  log_step "Checking Rust toolchain..."
  if ! command_exists rustc; then
    log_warn "Rust not found. Installing via rustup..."
    curl -sSf https://sh.rustup.rs | sh -s -- -y
  fi

  if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
  fi

  if ! command_exists rustc; then
    log_error "Rust installation failed."
    exit 1
  fi

  # Update Rust to ensure we have the latest stable
  log_step "Updating Rust toolchain..."
  rustup update stable 2>/dev/null || true

  log_info "Rust toolchain ready: $(rustc --version)"
}

# =============================================================================
# Install Tauri CLI
# =============================================================================

ensure_tauri_cli() {
  log_step "Checking Tauri CLI..."
  
  if command_exists cargo; then
    # Check if tauri-cli is installed
    if ! cargo install --list 2>/dev/null | grep -q "tauri-cli"; then
      log_warn "Installing Tauri CLI..."
      cargo install tauri-cli 2>/dev/null || log_warn "tauri-cli install skipped (using npm)"
    else
      log_info "Tauri CLI ready."
    fi
  fi
}

# =============================================================================
# Clear Caches
# =============================================================================

clear_caches() {
  log_step "Clearing all caches..."
  
  # Clear Tauri/Rust target directory (can cause stale build issues)
  if [ -d "$ROOT_DIR/client/src-tauri/target" ]; then
    log_info "Clearing Rust build cache..."
    rm -rf "$ROOT_DIR/client/src-tauri/target"
  fi
  
  # Clear Vite cache
  rm -rf "$ROOT_DIR/client/node_modules/.vite" 2>/dev/null || true
  
  # Clear npm cache for this project
  rm -rf "$ROOT_DIR/client/node_modules/.cache" 2>/dev/null || true
  
  # Clear Tauri dev cache
  rm -rf "$ROOT_DIR/client/src-tauri/target/debug/.fingerprint" 2>/dev/null || true
  
  # Clear npm global cache (helps with dependency issues)
  npm cache clean --force 2>/dev/null || true
  
  # Clear Cargo cache for this project
  rm -rf "$HOME/.cargo/registry/cache" 2>/dev/null || true
  
  # Clear any WebKit/browser cache for Tauri webview
  rm -rf "$HOME/Library/WebKit/com.thenashlab.hivemind.client" 2>/dev/null || true
  rm -rf "$HOME/Library/Caches/com.thenashlab.hivemind.client" 2>/dev/null || true
  
  log_info "Caches cleared."
}

# =============================================================================
# Install Node Dependencies
# =============================================================================

ensure_node_modules() {
  local app_dir="$1"
  if [ ! -d "$app_dir/node_modules" ]; then
    log_step "Installing Node dependencies for $(basename "$app_dir")..."
    (cd "$app_dir" && npm install)
  else
    log_info "$(basename "$app_dir") dependencies already installed."
  fi
}

# =============================================================================
# Get Server URL (auto-detect when possible)
# =============================================================================

get_server_url() {
  local saved_url=""

  # Check for saved config
  if [ -f "$CONFIG_FILE" ]; then
    saved_url="$(grep '^API_URL=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || true)"
  fi

  echo ""
  echo "=============================================="
  echo "   HIVEMIND SERVER CONNECTION"
  echo "=============================================="
  echo ""

  # 1. Try production server first
  log_step "Checking production server..."
  if curl -s --connect-timeout 3 "https://www.thenashlabhivemind.com/health" >/dev/null 2>&1 || \
     curl -s --connect-timeout 3 "https://www.thenashlabhivemind.com/docs" >/dev/null 2>&1; then
    log_info "Connected to production server!"
    export VITE_API_URL="https://www.thenashlabhivemind.com"
    mkdir -p "$(dirname "$CONFIG_FILE")"
    echo "API_URL=$VITE_API_URL" > "$CONFIG_FILE"
    return
  fi

  # 2. Try localhost (same machine) - check common ports
  log_step "Checking for local cloud server..."
  for port in 8080 8000 9000; do
    if curl -s --connect-timeout 2 "http://localhost:$port/health" >/dev/null 2>&1 || \
       curl -s --connect-timeout 2 "http://localhost:$port/docs" >/dev/null 2>&1; then
      log_info "Found cloud server running locally on port $port!"
      export VITE_API_URL="http://localhost:$port"
      mkdir -p "$(dirname "$CONFIG_FILE")"
      echo "API_URL=$VITE_API_URL" > "$CONFIG_FILE"
      return
    fi
  done

  # 3. Try saved URL if we have one
  if [ -n "$saved_url" ]; then
    log_step "Checking saved server: $saved_url"
    if curl -s --connect-timeout 3 "$saved_url/health" >/dev/null 2>&1 || \
       curl -s --connect-timeout 3 "$saved_url/docs" >/dev/null 2>&1; then
      log_info "Connected to saved server!"
      export VITE_API_URL="$saved_url"
      return
    else
      log_warn "Saved server not reachable."
    fi
  fi

  # 4. No auto-detection worked — ask the user
  log_warn "No cloud server detected automatically."
  echo ""
  echo "Enter the Hivemind Cloud server URL."
  echo "Examples:"
  echo "  - http://192.168.1.100:8000 (local network)"
  echo "  - https://hivemind.yourdomain.com (internet)"
  echo ""
  read -p "Server URL: " server_url

  if [ -z "$server_url" ]; then
    log_error "No URL entered. Cannot continue without a server."
    exit 1
  fi

  # Save config
  mkdir -p "$(dirname "$CONFIG_FILE")"
  echo "API_URL=$server_url" > "$CONFIG_FILE"

  export VITE_API_URL="$server_url"
  log_info "Using server: $VITE_API_URL"
}

# =============================================================================
# Test Server Connection
# =============================================================================

test_server_connection() {
  log_step "Verifying connection to $VITE_API_URL..."

  if curl -s --connect-timeout 5 "$VITE_API_URL/health" >/dev/null 2>&1 || \
     curl -s --connect-timeout 5 "$VITE_API_URL/docs" >/dev/null 2>&1; then
    log_info "Server connection verified!"
    return 0
  else
    log_error "Cannot reach server at $VITE_API_URL"
    echo ""
    echo "Make sure:"
    echo "  1. The cloud server is running (use Launch Cloud.app)"
    echo "  2. The URL is correct"
    echo "  3. Firewall allows the connection"
    echo ""
    exit 1
  fi
}

# =============================================================================
# Launch Client App
# =============================================================================

launch_client() {
  log_step "Launching Hivemind Client..."
  cd "$ROOT_DIR/client"

  echo ""
  log_info "Starting Client app (connected to $VITE_API_URL)..."
  echo ""

  npm run tauri dev
}

# =============================================================================
# Main
# =============================================================================

main() {
  echo ""
  echo "=============================================="
  echo "       HIVEMIND CLIENT SETUP"
  echo "=============================================="
  echo ""
  echo "This will install all prerequisites and launch"
  echo "the Hivemind Client application."
  echo ""

  if [ "$(uname -s)" != "Darwin" ]; then
    log_error "This setup currently supports macOS only."
    exit 1
  fi

  configure_noninteractive
  clear_caches
  ensure_xcode_clt
  ensure_homebrew
  ensure_node
  ensure_rust
  ensure_tauri_cli
  ensure_node_modules "$ROOT_DIR/client"
  get_server_url
  test_server_connection
  
  echo ""
  echo "=============================================="
  echo "   SETUP COMPLETE - LAUNCHING CLIENT"
  echo "=============================================="
  echo ""
  
  launch_client
}

main "$@"
