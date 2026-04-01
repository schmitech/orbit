#!/bin/bash
#
# get-auth-token.sh - Retrieve the ORBIT admin bearer token
#
# DESCRIPTION:
#   Detects the current platform and credential storage method,
#   then prints the raw bearer token to stdout. Works on macOS,
#   Linux (GNOME Keyring, KDE Wallet), headless servers (file
#   fallback), and WSL.
#
#   Requires a prior `orbit login` as an admin user.
#
# USAGE:
#   ./get-auth-token.sh              # Print the token
#   ./get-auth-token.sh --export     # Print as export statement
#   ./get-auth-token.sh --quiet      # Token only, no status messages
#
# EXAMPLES:
#   # Store in a variable
#   TOKEN=$(./get-auth-token.sh --quiet)
#
#   # Use with curl
#   curl -H "Authorization: Bearer $(./get-auth-token.sh --quiet)" \
#     http://localhost:3000/admin/adapters/info
#
#   # Use with template diagnostics tool
#   python server/tools/test_template_query.py \
#     --query "salary stats" --adapter intent-sql-sqlite-hr \
#     --api-key "$(./get-auth-token.sh --quiet)"
#
#   # Export for current shell session
#   eval "$(./get-auth-token.sh --export)"
#   echo $ORBIT_TOKEN

set -euo pipefail

KEYRING_SERVICE="orbit-cli"
KEYRING_ACCOUNT="auth-token"
ENV_FILE="$HOME/.orbit/.env"
QUIET=false
EXPORT=false

for arg in "$@"; do
  case "$arg" in
    --quiet|-q) QUIET=true ;;
    --export|-e) EXPORT=true; QUIET=true ;;
    --help|-h)
      head -35 "$0" | tail -32 | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

info() {
  if [ "$QUIET" = false ]; then
    echo "$@" >&2
  fi
}

error() {
  echo "Error: $@" >&2
  exit 1
}

# --- macOS Keychain ---
try_macos_keychain() {
  if command -v security &>/dev/null; then
    token=$(security find-generic-password -s "$KEYRING_SERVICE" -a "$KEYRING_ACCOUNT" -w 2>/dev/null) || return 1
    if [ -n "$token" ]; then
      info "Retrieved token from macOS Keychain"
      echo "$token"
      return 0
    fi
  fi
  return 1
}

# --- GNOME Keyring (Ubuntu, Debian, Fedora) ---
try_gnome_keyring() {
  if command -v secret-tool &>/dev/null; then
    token=$(secret-tool lookup service "$KEYRING_SERVICE" account "$KEYRING_ACCOUNT" 2>/dev/null) || return 1
    if [ -n "$token" ]; then
      info "Retrieved token from GNOME Keyring"
      echo "$token"
      return 0
    fi
  fi
  return 1
}

# --- KDE Wallet ---
try_kde_wallet() {
  if command -v kwallet-query &>/dev/null; then
    token=$(kwallet-query kdewallet -f "$KEYRING_SERVICE" -r "$KEYRING_ACCOUNT" 2>/dev/null) || return 1
    if [ -n "$token" ]; then
      info "Retrieved token from KDE Wallet"
      echo "$token"
      return 0
    fi
  fi
  return 1
}

# --- Python keyring (cross-platform fallback) ---
try_python_keyring() {
  if command -v python3 &>/dev/null; then
    token=$(python3 -c "
try:
    import keyring
    t = keyring.get_password('$KEYRING_SERVICE', '$KEYRING_ACCOUNT')
    if t: print(t)
except Exception:
    pass
" 2>/dev/null)
    if [ -n "$token" ]; then
      info "Retrieved token via Python keyring"
      echo "$token"
      return 0
    fi
  fi
  return 1
}

# --- File fallback (~/.orbit/.env) ---
try_file_storage() {
  if [ ! -f "$ENV_FILE" ]; then
    return 1
  fi

  # Try plain text first
  token=$(grep '^API_ADMIN_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [ -n "$token" ]; then
    info "Retrieved token from $ENV_FILE (plain text)"
    echo "$token"
    return 0
  fi

  # Try base64-encoded fallback
  encoded=$(grep '^API_ADMIN_TOKEN_B64=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [ -n "$encoded" ]; then
    token=$(echo "$encoded" | base64 --decode 2>/dev/null) || return 1
    if [ -n "$token" ]; then
      info "Retrieved token from $ENV_FILE (base64)"
      echo "$token"
      return 0
    fi
  fi

  return 1
}

# --- Detect platform and try methods in order ---
detect_and_retrieve() {
  local os_type
  os_type=$(uname -s 2>/dev/null || echo "Unknown")

  case "$os_type" in
    Darwin)
      info "Detected: macOS"
      try_macos_keychain && return 0
      try_python_keyring && return 0
      try_file_storage && return 0
      ;;
    Linux)
      # Check for WSL
      if grep -qi microsoft /proc/version 2>/dev/null; then
        info "Detected: WSL (Windows Subsystem for Linux)"
      elif [ -f /sys/hypervisor/uuid ] || [ -f /sys/devices/virtual/dmi/id/bios_vendor ]; then
        vendor=$(cat /sys/devices/virtual/dmi/id/bios_vendor 2>/dev/null || echo "")
        case "$vendor" in
          *Amazon*) info "Detected: AWS EC2" ;;
          *Google*) info "Detected: Google Cloud" ;;
          *Microsoft*) info "Detected: Azure VM" ;;
          *) info "Detected: Linux (cloud/VM)" ;;
        esac
      else
        info "Detected: Linux"
      fi
      # Try keyring daemons first, then file fallback for headless
      try_gnome_keyring && return 0
      try_kde_wallet && return 0
      try_python_keyring && return 0
      try_file_storage && return 0
      ;;
    MINGW*|MSYS*|CYGWIN*)
      info "Detected: Windows (Git Bash / MSYS)"
      try_python_keyring && return 0
      try_file_storage && return 0
      ;;
    *)
      info "Detected: $os_type (unknown platform)"
      try_python_keyring && return 0
      try_file_storage && return 0
      ;;
  esac

  return 1
}

# --- Main ---
token=$(detect_and_retrieve) || error "Could not retrieve auth token. Have you run 'orbit login' as an admin user?"

if [ "$EXPORT" = true ]; then
  echo "export ORBIT_TOKEN=\"$token\""
else
  echo "$token"
fi
